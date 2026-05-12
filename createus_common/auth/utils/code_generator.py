# filename: createus_common/auth/utils/code_generator.py

import random
import string


def generate_verification_code(length=6):
    return "".join(
        random.choices(string.digits, k=length)
    )
