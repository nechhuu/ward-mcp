import os
import pickle
import random
import subprocess
from pathlib import Path

import sqlite3


def sql_injection_vulnerable(user_input):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{user_input}'"
    cursor.execute(query)
    return cursor.fetchall()


def command_injection_vulnerable(filename):
    os.system(f"cat {filename}")
    subprocess.call(f"ls {filename}", shell=True)


def hardcoded_credentials():
    api_key = "sk-1234567890abcdef"
    password = "admin123"
    secret_token = "ghp_1234567890abcdefghijklmnopqrstuv"
    return api_key, password, secret_token


def insecure_random_usage():
    token = random.randint(0, 1000000)
    session_id = str(random.random())
    return token, session_id


def eval_usage(user_code):
    result = eval(user_code)
    exec(user_code)
    return result


def pickle_deserialization(data):
    obj = pickle.loads(data)
    return obj


def assert_for_security(is_admin):
    assert is_admin, "User must be admin"
    print("Admin access granted")


def path_traversal(user_path):
    file_path = f"/var/www/uploads/{user_path}"
    with open(file_path, 'r') as f:
        return f.read()


def weak_hash():
    import hashlib
    password = "secret123"
    hashed = hashlib.md5(password.encode()).hexdigest()
    return hashed


def flask_xss():
    from flask import Flask, request
    app = Flask(__name__)

    @app.route('/search')
    def search():
        query = request.args.get('q')
        return f"<html><body>Results for: {query}</body></html>"


def insecure_temp_file():
    import tempfile
    temp = tempfile.mktemp()
    with open(temp, 'w') as f:
        f.write("sensitive data")


async def http_without_timeout():
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")
        return response.json()
