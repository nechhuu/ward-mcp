def process_users(user_ids):
    import json

    results = []
    for uid in user_ids:
        user = db.query(User).filter(User.id == uid).first()
        results.append(user)
    return results


async def fetch_all_data():
    import requests

    data = requests.get("https://api.example.com/data")

    await some_async_call()

    another_async_call()

    return data


def unsafe_handler():
    try:
        do_risky_operation()
    except Exception as e:
        log_error(e)
