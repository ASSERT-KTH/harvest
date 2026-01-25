import keyring
login_keyring=keyring.get_keyring()
ieeexplore_key=login_keyring.get_password('login2', "ieeexplore_key")
semanticscholar_key=login_keyring.get_password('login2', "semanticscholar_key")
sciencedirect_key=login_keyring.get_password('login2', "sciencedirect_key")
springernature_key=login_keyring.get_password('login2', "springernature_key")

