from collections import Counter
import re
import sys
from bs4 import BeautifulSoup
import Levenshtein as lev

from typing import Any, Dict, List, Union
import warnings

from src.utils.noise_detection import split_identifier_into_parts
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

from tree_sitter import Node
from src.utils.parser.language_parser import tokenize_docstring, traverse_type


REGEX_TEXT = ("(?<=[a-z0-9])(?=[A-Z])|"
              "(?<=[A-Z0-9])(?=[A-Z][a-z])|"
              "(?<=[0-9])(?=[a-zA-Z])|"
              "(?<=[A-Za-z])(?=[0-9])|"
              "(?<=[@$.'\"])(?=[a-zA-Z0-9])|"
              "(?<=[a-zA-Z0-9])(?=[@$.'\"])|"
              "_|\\s+")

if sys.version_info >= (3, 7):
    import re
    SPLIT_REGEX = re.compile(REGEX_TEXT)
else:
    import regex
    SPLIT_REGEX = regex.compile("(?V1)"+REGEX_TEXT)
    

def split_identifier_into_parts(identifier: str) -> List[str]:
    """
    Split a single identifier into parts on snake_case and camelCase
    """
    identifier_parts = list(s.lower() for s in SPLIT_REGEX.split(identifier) if len(s)>0)

    if len(identifier_parts) == 0:
        return [identifier]
    return identifier_parts


def check_node_error(node: Node) -> bool:
    """
    Check if node contains "ERROR" node
    Args:
        node (tree_sitter.Node): node
    
    Return:
        bool
    """
    if not isinstance(node, Node):
        raise ValueError("Expect type tree_sitter.Node, get %i", type(node))

    error_node = []        
    traverse_type(node, error_node, ['ERROR'])
    if len(error_node) > 0:
        return True
    else:
        return False


def get_node_length(node: Node) -> int:
    """
    Get node length
    Args:
        node (tree_sitter.Node): node
        
    Return:
        int
    """
    if not isinstance(node, Node):
        raise ValueError("Expect type tree_sitter.Node, get %i", type(node))

    line_start = node.start_point[0]
    line_end = node.end_point[0]
    return int(line_end - line_start)
    
    
def remove_comment_delimiters(docstring: str) -> str:
    """
    :param comment: raw (line or block) comment
    :return: list of comment lines
    """
    clean_p1 = re.compile('([\s\/*=-]+)$|^([\s\/*!=#-]+)')
    clean_p2 = re.compile('^([\s*]+)')

    def func(t):
        t = t.strip().replace('&nbsp;', ' ')
        return re.sub(clean_p2, '', t).strip()

    comment_list = []
    for line in re.sub(clean_p1, '', docstring).split('\n'):
        cur_line = func(line)
        if cur_line != '':
            comment_list.append(cur_line)

    return comment_list


def remove_special_tag(docstring: str) -> str:
    """
    Remove all special tag (html tag, e.g. <p>docstring</p>)
    """
    return BeautifulSoup(docstring, "html.parser").get_text()


def remove_special_character(docstring: str) -> str:
    return re.sub(r'[^a-zA-Z0-9\\\_\.\,]', ' ', docstring)


def remove_url(docstring: str, replace: str='') -> str:
    """
    Replace URL (e.g. https://google.com) by `replace` word
    """
    return re.sub(r'http\S+', replace, docstring, flags=re.MULTILINE)


def remove_unrelevant(docstring: str) -> str:
    """
    (e.g asdfasdfasdf)
    (ie. asdfasdf)
    """
    pattern1 = re.compile(r'\((i\.e|e\.g|\beg|\bie).*?\)')
    docstring = re.sub(pattern1, '', docstring)
    
    return docstring


def check_black_node(node_name: str, exclude_list: List = None):
    """
    Check if node belongs to black list. E.g:
        - Built-in function
        - Test function, test class
        - Constructor
    """
    black_keywords = ['test_', 'Test_', '_test', 'toString', 'constructor', 'Constructor']
    black_keywords.extend(exclude_list)
    
    if not isinstance(node_name, str):
        raise ValueError(f'Expect str, get {type(node_name)}')
    if node_name.startswith('__') and node_name.endswith('__'):
        return True
    if node_name.startswith('set') or node_name.startswith('get'):
        return True
    if any(keyword in node_name for keyword in black_keywords):
        return True
    
    return False


def check_function_empty(node):
    # for child in node.children:
    #     if child.type == 'block':
    #         for item in child.children:
    #             if item.type == 'comment' or (item.type == 'expression_statement' and item.children[0].type == 'string'):
    #                 continue
    #             elif item.type != 'pass_statement' and item.type != 'raise_statement':
    #                 return False
    if get_node_length(node) <= 3:
        return False
    return True


def check_autogenerated_by_code(raw_code: str, identifier: str):
    threshold = 0.4
    fn_name_splited = split_identifier_into_parts(identifier)
    fn_name_splited = ' '.join(fn_name_splited).lower()
    
    comment = str(re.sub(r'[^a-zA-Z0-9]', ' ', comment)).lower()

    d0 = lev.distance(fn_name_splited, comment)
    d1 = max(len(fn_name_splited), len(comment))
    
    if d0 <= d1*threshold:
        # print('Auto-code')
        return True
    
    return False


def check_docstring_length(docstring: str):
    doc_tokens = docstring.strip().split()
    if len(doc_tokens) <= 3 or len(doc_tokens) >= 256:
    # if len(doc_tokens) >= 256:
        return True
    return False


def check_docstring_literal(docstring: str):
    p = re.compile('[a-zA-Z]')
    if not docstring.isascii():
        return True
    elif not p.search(docstring):
        return True
    else:
        return False


def check_docstring_contain_question(docstring: str):
    pattern = re.compile(r'(?i)^(why\b|how\b|what\'?s?\b|where\b|is\b|are\b)')

    if docstring[-1] == '?' or pattern.search(docstring):
        return True
    else:
        return False


def check_docstring_underdevelopment(docstring: str):
    p1 = re.compile('(?i)^((Description of the Method)|(NOT YET DOCUMENTED)|(Missing[\s\S]+Description)|(not in use)|'
                    '(Insert the method\'s description here)|(No implementation provided)|(\(non\-Javadoc\)))')
    p2 = re.compile('(?i)^(todo|deprecate|copyright|fixme)')
    p3 = re.compile('^[A-Za-z]+(\([A-Za-z_]+\))?:')
    p4 = re.compile('[A-Z ]+')
    p5 = re.compile('\(.+\)|\[.+\]|\{.+\}')

    if p1.search(docstring) or p2.search(docstring) or p3.search(docstring):
        return True
    elif re.fullmatch(p4, docstring) or re.fullmatch(p5, docstring):
        return True
    else:
        return False


def check_docstring_autogenerated(docstring: str):
    p1 = re.compile(r'(?i)@[a-zA-Z]*generated\b')
    p2 = re.compile('(?i)^([aA]uto[-\s]generated)')
    p3 = re.compile('(?i)^(This method initializes)')
    p4 = re.compile('(?i)^(This method was generated by)')

    if docstring is not None:
        if p1.search(docstring):
            return True

    if p2.search(docstring) or p3.search(docstring) or p4.search(docstring):
        return True
    
    else:
        return False


def check_contain_little_single_char(docstring: str):
    threshold = 0.7
    docstring = "".join(docstring.strip().split())
    if len(docstring) <= 1:
        return True
    num_alphabet_chars = len(re.findall("[a-zA-Z]", docstring))

    return num_alphabet_chars / len(docstring) < threshold


def check_contain_many_special_char(docstring: str):
    if docstring.strip() == "":
        return True
    # b = False
    num_words = len(tokenize_docstring(docstring))
    counter = Counter(docstring)

    count = 0
    signs = [",", ".", ";", ":", "\\", "/", "\?", "{", "}", "[", "]", "'", '"', "-", "+", "=", "(", ")", "\#", "*", "<", ">", "~", "%",]
    # if language != "python":
    #     signs.append("_")
    # signs = ["_"]

    for sign in signs:
        count += counter[sign]
        # b = b or (counter[sign] > 3 and counter[sign] / num_words > 0.2)
    return count > 3 and count / num_words > 0.4


def check_contain_many_special_case(docstring: str):
    """
    Check if the string contains too much sneak_case or camelCase
    """
    threshold = 0.3
    total_words = docstring.strip().split()
    if len(total_words) == 0:
        return True
    sneak_cases = re.findall("\w+_\w+", docstring)
    camelCases = re.findall("[A-Z]([A-Z0-9]*[a-z][a-z0-9]*[A-Z]|[a-z0-9]*[A-Z][A-Z0-9]*[a-z])[A-Za-z0-9]*", docstring)
    return (len(sneak_cases) + len(camelCases))/len(total_words) > threshold


def check_contain_many_repeated_word(docstring: str):
    """
    Check if the string (longer than 30 words) have too many repeated word
    """
    threshold = 0.4
    docstring = "".join(docstring.strip().split())
    counter = Counter(docstring)
    return len(docstring) > 30 and counter.most_common()[0][1] / len(docstring) > threshold


def check_contain_many_uppercase_word(docstring: str):
    for pattern in ["DD", "MM", "YY", "YYYY"]:
        docstring = docstring.replace(pattern, pattern.lower())

    docstring = docstring.strip()

    uppercase_words = re.findall("[A-Z][A-Z0-9]+", docstring)
    docstring_tokens = docstring.strip().split()
    return len(docstring_tokens) > 4 and len(uppercase_words) / len(docstring_tokens) > 0.3


def check_contain_many_long_word(docstring: str):
    docstring_tokens = docstring.strip().split()
    if not docstring_tokens:
        return True
    docstring_tokens_ = []
    for docstring_token in docstring_tokens:
        docstring_tokens_.extend(docstring_token.strip().split("_"))
    docstring_tokens = docstring_tokens_
    return max([len(docstring_token) for docstring_token in docstring_tokens]) > 30


def check_function(node, node_metadata: Dict[str, Any], exclude_list: List = None, is_class=False):
    """
    Check function if
        - is built-in function (python)
        - is constructor
        - is empty 
        - is error node
        - have length < 3 lines
    
    Args:
        node (tree_sitter.Node): function node
        exclude_list (List): exclude name of function
    Return:
        bool: pass the check or not
    """
    node_identifier = node_metadata['identifier']
    
    # Check node/code
    if check_node_error(node):
        return False
    if check_black_node(node_identifier, exclude_list):
        return False
    if check_function_empty(node):
        return False
    
    return True


def check_docstring(docstring: str):
    """
    Check docstring is valid or not
    """
    check_funcs_mapping = [
        # 'check_docstring_length',
        'check_docstring_literal',
        'check_docstring_contain_question',
        'check_docstring_underdevelopment',
        'check_docstring_autogenerated',
        'check_contain_little_single_char',
        # 'check_contain_many_special_char',
        'check_contain_many_special_case',
        'check_contain_many_repeated_word',
        'check_contain_many_uppercase_word',
        'check_contain_many_long_word',
    ]
    
    check_docstring_funcs = [
        # check general
        # check_docstring_length,
        check_docstring_literal,
        check_docstring_contain_question,
        check_docstring_underdevelopment,
        check_docstring_autogenerated,
        # check special cases
        check_contain_little_single_char,
        # check_contain_many_special_char,
        check_contain_many_special_case,
        check_contain_many_repeated_word,
        check_contain_many_uppercase_word,
        check_contain_many_long_word,
    ]
    
    # docstring_list = docstring.split('.')
    # print(f'\nAfter split {docstring_list}')
    
    applied_res = []
    result = False
    for i, check_condition in zip(check_funcs_mapping, check_docstring_funcs):
        # for comment in docstring_list:
        if docstring == '' or not docstring:
            return True, []
        # if True then docstring have fail
        if check_condition(docstring):
            result = True
            # return True
            applied_res.append(f"<{i}> {docstring}")
    
    return result, applied_res


def clean_docstring(docstring: str):
    """
    Clean docstring by removing special tag/url, characters, unrelevant information
    """
    cleaned_docstring = []
    # docstring_list = remove_comment_delimiters(docstring)
    _docstring = '\n'.join(remove_comment_delimiters(docstring))
    _docstring = remove_unrelevant(_docstring)
    docstring_list = _docstring.strip().split('\n')  # split end line -> split by "."

    for line in docstring_list:
        line = remove_special_tag(line) # <xml> </xml>
        is_pass, res = check_docstring(line)
        if not is_pass:
            line = remove_url(line)
            cleaned_docstring.append(line)
        else:
            break

    cleaned_docstring = '\n'.join(cleaned_docstring)
    # cleaned_docstring = remove_special_character(cleaned_docstring)
    
    cleaned_docstring = cleaned_docstring.strip()
    # valid condition
    if clean_docstring == '' or check_docstring_length(cleaned_docstring):
        return None, res
    
    return cleaned_docstring, res


if __name__ == '__main__':
    # test remove comment delimiters
    raw = [
        '// C, C++, C#',
        '/// C, C++, C#',   
        
        '/*******'
        '* Java'
        '/*******',
        '//** Java */',
        
        '# Python', 
        
        '//! Rust',
        '//!!! Rust',
        '/*!! Rust',
        '/*! Rust',
        
        '''
        /* The code below will print the words Hello World to the screen, and it is amazing 
        
        Somethin here too*/
        '''
    ]

    # for item in raw:
    #     print(remove_comment_delimiters(item))
        
    samples = [
        '/* 将JSONArray转换为Bean的List, 默认为ArrayList */',
        '// TODO: Why is he using Math.round?',
        '/* for now try mappig full type URI */',
        '// public String transformTypeID(URI typeuri){',
        '// return typeuri.toString();}',
        '/* Do we need to show the upgrade wizard prompt? */',
        '/* fixme: This function is not in use */',
        '// SampleEncryptionBox (senc) and SampleAuxiliaryInformation{Sizes|Offsets}Box',
        '/* This method initializes by me */',
        '/* @func_name_generated',
        '/* Auto-generated by IDE',
        '/ Auto-generated by IDE',
    ]
    
    for item in samples:
        print(clean_docstring(item))
        
    samples = [
        '''
        Returns the Surface's pixel buffer if the Surface doesn't require locking.
        (e.g. it's a software surface)
        ''',
        '''
        Taking in a sequence string, return the canonical form of the sequence
        (e.g. the lexigraphically lowest of either the original sequence or its
        reverse complement)
        ''',
        '''
        Internal clear timeout. The function checks that the `id` was not removed
        (e.g. by `chart.destroy()`). For the details see
        [issue #7901](https://github.com/highcharts/highcharts/issues/7901).
        ''',
    ]
    
    print('==== Cleaning ====')
    for item in samples:
        clean_docstring(item)
        
    sample = """
    _restructure - The function to be called after
adding/removing data to the node.
This is used in implementations that involve post-insertion
processes of the tree (for example, rebalancing in B+ tree
derivatives).
The function will only restructure the immediate children of `this`
or `this` if it is a root node. It will assume all grandchildren
(if any) has been already restructured correctly.
For trees that do not implement post-insertion processes, return
`this`.
@memberof GiveNonLeafNode.prototype

@returns {give.GiveNonLeafNode|Array<give.GiveNonLeafNode>|false}
This shall reflect whether there are any changes in the tree
structure for root and non-root nodes:
* For root nodes, always return `this` (cannot delete root even
without any children).
* For inner nodes (or leaf), if the node should be removed (being
merged with its sibling(s) or becoming an empty node, for
example), return `false`. Return `this` in all other cases.
    """
    clean_docstring(sample)