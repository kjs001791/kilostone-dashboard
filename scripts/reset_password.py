import bcrypt

password = input("새 비밀번호 입력: ").encode("utf-8")
hashed = bcrypt.hashpw(password, bcrypt.gensalt()).decode("utf-8")

print("\n아래 값을 .env의 ADMIN_PASSWORD_HASH= 에 붙여넣으세요:\n")
print(hashed)
