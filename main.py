from bot import dp, start_bot

if __name__ == '__main__':
    try:
        start_bot(dp)
    except Exception as exception:
        print(exception)