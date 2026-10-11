"""Redact secrets before displaying or persisting protocol exceptions."""
import re


def redact_message(message, secrets=()):
    text = str(message)
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    text = re.sub(r'-----BEGIN .*?PRIVATE KEY-----.*?-----END .*?PRIVATE KEY-----',
                  '[redacted private key]', text, flags=re.DOTALL)
    text = re.sub(r'(?i)\b(password|passwd|token|api[_-]?key|authorization)(\s*[:=]\s*)[^\s,;]+',
                  r'\1\2[redacted]', text)
    return ''.join(c for c in text if ord(c) >= 32 or c == '\n')[:2000]
