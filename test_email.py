# Salve como test_email.py e rode: python test_email.py
import os
from dotenv import load_dotenv
load_dotenv()
from email_utils import email_codigo

resultado = email_codigo("willianngsantos@gmail.com", "123456", "reset_senha")
print("Enviado!" if resultado else "FALHOU — verifique o terminal acima")