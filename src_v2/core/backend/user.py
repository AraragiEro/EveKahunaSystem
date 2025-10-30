from enum import Enum


class User:
    def __init__(self, id, name, email, passwd_hash):
        self.id = id
        self.name = name
        self.email = email
        self.password_hash = passwd_hash
        self.user_data = UserData()

class UserData:
    def __init__(self):
        self.role = []
