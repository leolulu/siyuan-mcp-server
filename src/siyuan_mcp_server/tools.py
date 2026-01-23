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


if __name__ == "__main__":
    test_string = """
- Todoist token
数据库连接: jdbc:mysql://localhost:3306/mydb?user=admin&password=secret123
API密钥: sk_test_1234567890abcdefghijklmnopqrstuvwxyz
令牌: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
用户名: user1, 密码: P@ssw0rd!
"""
    print(mask_sensitive_data(test_string))
