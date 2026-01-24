import re


def mask_middle_third(text):
    """
    只打码字符串中间1/3的部分，保留开头和结尾部分

    参数:
        text (str): 输入的字符串

    返回:
        str: 处理后的字符串，中间1/3部分被替换为*
    """
    if len(text) < 6:  # 如果字符串太短，直接全部打码
        return "*" * len(text)

    # 计算各个部分的长度
    third = len(text) // 3
    start_length = (len(text) - third) // 2
    end_length = len(text) - third - start_length

    # 构建结果字符串
    result = text[:start_length] + ("*" * third) + text[-end_length:] if end_length > 0 else text[:start_length] + ("*" * third)

    return result


def is_siyuan_block_id(text: str) -> bool:
    """
    判断文本是否为思源块ID
    
    格式: 14位时间戳(YYYYMMDDHHMMSS) + "-" + 任意长度字母数字后缀
    例如: 20250325142648-fuih8um
    """
    # 允许任意长度的字母数字后缀
    pattern = r'^\d{14}-[a-zA-Z0-9]+$'
    return bool(re.match(pattern, text.strip()))


def is_siyuan_timestamp(text: str) -> bool:
    """
    判断文本是否为思源时间戳
    
    格式: 14位纯数字 (YYYYMMDDHHMMSS)
    例如: 20250325161145
    """
    pattern = r'^\d{14}$'
    return bool(re.match(pattern, text.strip()))


def mask_sensitive_data(text):
    """
    对文本中的敏感信息（密钥、API Key、Secret等）进行打码处理

    参数:
        text (str): 输入的文本

    返回:
        str: 处理后的文本，其中敏感信息被替换为*
    """
    # 定义各种密钥格式的正则表达式模式
    patterns = [
        # AWS Access Key ID: AKIA开头，20个字符
        (r"AKIA[0-9A-Z]{16}", lambda m: mask_middle_third(m.group())),
        # AWS Secret Access Key: 40个字符的随机字符串
        (r"[A-Za-z0-9/+=]{40}", lambda m: mask_middle_third(m.group())),
        # GitHub Personal Access Token
        (
            r"ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|ghu_[a-zA-Z0-9]{36}|ghs_[a-zA-Z0-9]{36}|ghr_[a-zA-Z0-9]{36}",
            lambda m: mask_middle_third(m.group()),
        ),
        # JWT Token: 由三部分组成，用点分隔
        (r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", lambda m: mask_middle_third(m.group())),
        # UUID
        (r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", lambda m: mask_middle_third(m.group())),
        # API Key: 32位以上的字母数字组合
        (r"[A-Za-z0-9]{32,}", lambda m: mask_middle_third(m.group())),
        # OAuth tokens: 20位以上的字母数字组合
        (r"[A-Za-z0-9]{20,}", lambda m: mask_middle_third(m.group())),
        # Private Key
        (r"-----BEGIN(?: RSA)? PRIVATE KEY-----.*?-----END(?: RSA)? PRIVATE KEY-----", lambda m: mask_middle_third(m.group())),
        # Database URLs - 特殊处理，只打码密码部分
        (
            r"(postgresql|mysql|mongodb)://([^:]+):([^@]+)@([^/]+)/([^\s]+)",
            lambda m: f"{m.group(1)}://{m.group(2)}:{mask_middle_third(m.group(3))}@{m.group(4)}/{m.group(5)}",
        ),
        # API URLs with credentials - 特殊处理，只打码密钥值部分
        (r"(api[_-]?key[=:\s]+)([^\s&]+)", lambda m: f"{m.group(1)}{mask_middle_third(m.group(2))}"),
        # Base64编码的密钥
        (r"[A-Za-z0-9+/]{20,}={0,2}", lambda m: mask_middle_third(m.group())),
        # 十六进制密钥
        (r"[0-9a-fA-F]{32,}", lambda m: mask_middle_third(m.group())),
        # 带有引号的密钥
        (r"([\"\'])([A-Za-z0-9+/=]{20,})(\1)", lambda m: m.group(1) + mask_middle_third(m.group(2)) + m.group(3)),
        # 通用密钥格式：包含特殊字符的长字符串
        (r"[\"\']?[A-Za-z0-9_\-+/=]{20,}[\"\']?", lambda m: mask_middle_third(m.group())),
    ]

    # 应用所有模式
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.DOTALL)

    return result


def parse_and_mask_kramdown(kramdown: str) -> str:
    """
    智能mask kramdown，保留思源属性标记中的ID和时间戳
    
    Args:
        kramdown: kramdown格式的markdown字符串
        
    Returns:
        处理后的kramdown字符串，思源属性保留完整，用户内容被mask
    """
    # 1. 找出所有思源属性标记
    attr_pattern = r'\{:\s*([^}]+)\}'
    result = []
    last_pos = 0
    
    for match in re.finditer(attr_pattern, kramdown):
        # 2. 属性标记前的用户内容 -> mask
        user_content = kramdown[last_pos:match.start()]
        masked_user = mask_sensitive_data(user_content)
        result.append(masked_user)
        
        # 3. 属性标记本身 -> 智能替换，保留思源属性
        attrs_str = match.group(1)
        
        # 用正则逐个匹配 {key="value"} 或 {key='value'} 格式的属性
        def replace_attr_value(match):
            key = match.group(1)
            quote = match.group(2)  # 引号 " 或 '
            value = match.group(3)  # 值
            
            # 判断是否需要mask
            if is_siyuan_block_id(value) or is_siyuan_timestamp(value):
                return match.group(0)  # 保留原始
            else:
                masked_value = mask_sensitive_data(value)
                return f'{key}={quote}{masked_value}{quote}'
        
        # 匹配 pattern: key=("|')value\2
        # \1=key, \2=quote, \3=value
        attrs_result = re.sub(r'(\w+)=([\"\'])(.*?)\2', replace_attr_value, attrs_str)
        
        result.append('{:' + attrs_result + '}')
        last_pos = match.end()
    
    # 4. 最后剩余的用户内容 -> mask
    result.append(mask_sensitive_data(kramdown[last_pos:]))
    
    return ''.join(result)


if __name__ == "__main__":
    # 测试：思源ID应该保留
    kramdown = '- {: id="20250325142648-fuih8um" updated="20250325161145"}test content'
    print("原始:", repr(kramdown))
    print("结果:", repr(parse_and_mask_kramdown(kramdown)))
    print()
    
    # 测试：思源ID应该保留
    kramdown2 = '- {: id="20250325142648-fuih8um" updated="20250325161145"}test content'
    print("测试2 - 原始:", repr(kramdown2))
    print("测试2 - 结果:", repr(parse_and_mask_kramdown(kramdown2)))
