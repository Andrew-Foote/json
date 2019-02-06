from functools import partial
from collections import namedtuple
import sys

def empty_generator(f):
    def generator(*args, **kwargs):
        yield from ()
        return f(*args, **kwargs)

    return generator

class ParseError(Exception):
    def __init__(self, msg, index):
        super().__init__(msg)
        self.index = index

Token = namedtuple('Token', ['content', 'index'])

class ParseDir(Enum):
    begin_object = '{'
    end_object = '}'
    begin_array = '['
    end_array = ']'
    pair_separator = ':'
    list_separator = ','

def scan(src):
    proc = scan_space
    
    for i, char in enumerate(src):
        proc = yield from proc(char, i)

def scan_space(char, index):
    if char in ' \t\n\r':
        return scan_space
    elif char in '{}[]:,':
        yield Token(ParseDir(char), index)
        return scan_space
    elif char == '"':
        return partial(scan_string, chars=[])
    elif char == '0':
        yield Token(0, index)
        return scan_space
    elif char.isdigit():
        return partial(scan_number, val=int(char), sign=1)
    elif char == '-':
        return scan_minus
    elif char == 't':
        return partial(literal_name_scanner('true', True), chars=[])
    elif char == 'f':
        return partial(literal_name_scanner('false', False), chars=[])
    elif char == 'n':
        return partial(literal_name_scanner('null', None), chars=[])
    else:
        raise ParseError('invalid token', index)

def scan_string(char, index, *, chars):
    if char == '"':
        yield Token(''.join(chars), index)
        return scan_space
    elif char == '\\':
        return partial(scan_escape_sequence, chars=chars)
    elif ord(char) < 0x20:
        raise ParseError(f'invalid character (use \'\\u{ord(char):04x}\')', index)
    else:
        chars.append(char)
        return partial(scan_string, chars=chars)

@empty_generator
def scan_escape_sequence(char, index, *, chars):
    if char in '"\\/':
        chars.append(char)
        return partial(scan_string, chars=chars)
    elif char == 'b':
        chars.append('\b')
        return partial(scan_string, chars=chars)
    elif char == 'f':
        chars.append('\f')
        return partial(scan_string, chars=chars)
    elif char == 'n':
        chars.append('\n')
        return partial(scan_string, chars=chars)
    elif char == 'r':
        chars.append('\r')
        return partial(scan_string, chars=chars)
    elif char == 't':
        chars.append('\t')
        return partial(scan_string, chars=chars)
    elif char == 'u':
        return partial(scan_unicode_escape_sequence, chars=chars, val=0, digitcount=0)
    else:
        raise ParseError(f'invalid escape sequence', index)

@empty_generator
def scan_unicode_escape_sequence(char, index, *, chars, val, digitcount):
    if char.isdigit():
        val = val * 16 + int(char)

        if digitcount == 3:
            chars.append(chr(val))
            return partial(scan_string, chars=chars)
        else:
            return partial(scan_unicode_escape_sequence, chars=chars, val=val, digitcount=digitcount + 1)
    elif ord('a') < ord(char) < ord('z'):
        val = val * 16 + 10 + ord(char) - ord('a')

        if digitcount == 3:
            chars.append(chr(val))
            return partial(scan_string, chars=chars)
        else:
            return partial(scan_unicode_escape_sequence, chars=chars, val=val, digitcount=digitcount + 1)
    elif ord('A') < ord(char) < ord('Z'):
        val = val * 16 + 10 + ord(char) - ord('A')

        if digitcount == 3:
            chars.append(chr(val))
            return partial(scan_string, chars=chars)
        else:
            return partial(scan_unicode_escape_sequence, chars=chars, val=val, digitcount=digitcount + 1)
    else:
        raise ParseError('invalid Unicode escape sequence', index)

def scan_number(char, index, *, val, sign):
    if char.isdigit():
        return partial(scan_number, val=10 * val + int(char))
    elif char == '.':
        return partial(scan_just_after_decimal_point, val=val)
    elif char in 'eE':
        return partial(scan_just_after_exponent, val=val)
    elif char in ' \t\n\r':
        yield Token(sign * val, index)
        return scan_space
    elif char in '{}[]:,':
        yield Token(sign * val, index)
        yield Token(ParseDir(char), index)
        return scan_space
    elif char == '"':
        yield Token(sign * val, index)
        return partial(scan_string, chars=[])
    elif char == '-':
        yield Token(sign * val, index)
        return scan_minus
    elif char == 't':
        yield Token(sign * val, index)
        return literal_name_scanner('true')
    elif char == 'f':
        yield Token(sign * val, index)
        return literal_name_scanner('false')
    elif char == 'n':
        yield Token(sign * val, index)
        return literal_name_scanner('null')
    else:
        raise ParseError('invalid token', index)

def scan_just_after_decimal_point(char, index, *, val, sign):
    if char.isdigit():
        return partial(scan_after_decimal_point, val=val, sign=sign, numer=int(char), denom=10)
    else:
        raise ParseError('expected a digit', index)

def scan_after_decimal_point(char, index, *, val, sign, numer, denom):
    if char.isdigit():
        return partial(scan_after_decimal_point, val=val, sign=sign, numer=numer * 10 + int(char), denom=10 * denom)
    elif char in 'eE':
        return partial(scan_just_after_exponent, val=val + numer / denom, sign=sign)
    elif char in ' \t\n\r':
        yield Token(sign * (val + numer / denom), index)
        return scan_space
    elif char in '{}[]:,':
        yield Token(sign * (val + numer / denom), index)
        yield Token(ParseDir(char), index)
        return scan_space
    elif char == '"':
        yield Token(sign * (val + numer / denom), index)
        return partial(scan_string, chars=[])
    elif char == '-':
        yield Token(sign * (val + numer / denom), index)
        return scan_minus
    elif char == 't':
        yield Token(sign * (val + numer / denom), index)
        return literal_name_scanner('true')
    elif char == 'f':
        yield Token(sign * (val + numer / denom), index)
        return literal_name_scanner('false')
    elif char == 'n':
        yield Token(sign * (val + numer / denom), index)
        return literal_name_scanner('null')
    else:
        raise ParseError('invalid token', index)

def scan_just_after_exponent(char, index, *, val, sign):
    if char.isdigit():
        return partial(scan_after_exponent, val=val, sign=sign, exp=int(char), exp_sign=1)
    elif char == '+':
        return partial(scan_plus_after_exponent, val=val, sign=sign)
    elif char == '-':
        return partial(scan_minus_after_exponent, val=val, sign=sign)
    else:
        raise ParseError('expected a digit', index)

def scan_after_exponent(char, index, *, val, sign, exp, exp_sign):
    if char.isdigit():
        return partial(scan_after_exponent, val=val, sign=sign, exp=exp * 10 + int(char), exp_sign=exp_sign)
    elif char in ' \t\n\r':
        yield Token(sign * val ** (exp_sign * exp), index)
        return scan_space
    elif char in '{}[]:,':
        yield Token(sign * val ** (exp_sign * exp), index)
        yield Token(ParseDir(char), index)
        return scan_space
    elif char == '"':
        yield Token(sign * val ** (exp_sign * exp), index)
        return partial(scan_string, chars=[])
    elif char == '-':
        yield Token(sign * val ** (exp_sign * exp), index)
        return scan_minus
    elif char == 't':
        yield Token(sign * val ** (exp_sign * exp), index)
        return literal_name_scanner('true')
    elif char == 'f':
        yield Token(sign * val ** (exp_sign * exp), index)
        return literal_name_scanner('false')
    elif char == 'n':
        yield Token(sign * val ** (exp_sign * exp), index)
        return literal_name_scanner('null')
    else:
        raise ParseError('invalid token', index)

def scan_plus_after_exponent(char, index, *, val, sign):
    if char.isdigit():
        return partial(scan_after_exponent, val=val, sign=sign, exp=int(char), exp_sign=1)
    else:
        raise ParseError('expected a digit', index)

def scan_minus_after_exponent(char, index, *, val, sign):
    if char.isdigit():
        return partial(scan_after_exponent, val=val, sign=sign, exp=int(char), exp_sign=-1)
    else:
        raise ParseError('expected a digit', index)

def scan_minus(char, index):
    if char.isdigit():
        return partial(scan_number, val=int(char), sign=-1)
    else:
        raise ParseError('expected a digit', index)

def literal_name_scanner(name, val):
    def scan_name(char, index, *, chars):
        if len(chars) == len(name) - 1:
            yield Token(val, index)
            return scan_space
        elif char == name[len(chars)]:
            chars.append(char)
            return scan_name(char, index, chars=chars)
        else:
            raise ParseError(f'expected \'{name[len(chars)]}\' (to complete the literal name "{name}")')

def parse(tokens):
    val, index = parse_value(tokens, 0)
    
    if index < len(tokens):
        raise ParseError('trailing data', tokens[index].index)

    return val

def parse_value(tokens, index, char_index):
    try:
        token = tokens[index]
    except IndexError:
        raise ParseError('expected a value', char_index)

    content = token.content
    
    if content == ParseDir.begin_object:
        return parse_object(tokens, index + 1, token.index)
    elif content == ParseDir.begin_array:
        return parse_array(tokens, index + 1, token.index)
    elif isinstance(content, ParseDir):
        raise ParseError('expected a value', token.index)
    else:
        return content, 1

def parse_object(tokens, index, char_index):
    if len(tokens) < index + 3:
        raise ParseError('incomplete object', 
    
    obj = {}

    while True:
        try:
            token = tokens[index]
        except IndexError:
            raise ParseError('incomplete object', char_index)
            
        name = token.content

        if name == '}':
            return obj, index + 1

        if not isinstance(name, str):
            raise ParseError('invalid name (must be a string)', token.index)
    
        index += 1

        try:
            token = tokens[index]
        except IndexError:
            raise ParseError('expected a colon', token.index)

        if token.content != ':':
            raise ParseError('expected a colon', token.index)

        index += 1

        try:
            token = tokens[index]

if __name__ == '__main__' and '-i' in sys.argv[1:]:
    while True:
        print('>', end=' ')
        src = input()

        try:
            val = tuple(scan(src))
        except ParseError as error:
            print(f'  {" " * error.index}^')
            print(f'Error: {error}')
        else:
            print(val)
