import telebot
import openai
import sqlite3
import time
import json
import os
import dateparser
from datetime import timedelta, datetime

from dotenv import load_dotenv
_ = load_dotenv('/Users/andrey.nikulin/Development/Personal/.env')
openai.api_key = os.environ['GPT-3']
SYSTEM_MESSAGE = "You are a friendly and helpful assistant at BARBERRY'N'BLADES barber shop."

bot = telebot.TeleBot("6829769716:AAE23MFuahr41ulPQAQdYURTPwTSEGUSmKQ")
model = "gpt-3.5-turbo"
MAX_TOKENS = 2049

users = {}

@bot.message_handler(commands=['start'])
def start(message):

    user = _get_user(message.from_user.id)
    user['last_prompt_time'] = 0
    user['last_text'] = ''
    
    msgs = [
        f"Hey there, {message.from_user.first_name}!",
        "It's your personal bot-assistant from BARBERRY'N'BLADES, so thrilled to meet you!",
        "I'm your go-to guide for appointments - I'll not just line them up for you, but also remember them on your behalf (though I hope I never have to cancel any).",
        "So, what can I assist you with today in the realm of BARBERRY'N'BLADES?"
    ]

    logo = open('/Users/andrey.nikulin/Downloads/barberry.png','rb')
    bot.send_photo(message.chat.id, logo, caption=msgs[0])
    [bot.send_message(message.chat.id, mess) for mess in msgs[1:]]
    logo.close()

    conn = sqlite3.connect('userbase.sql')
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
                id int primary key,
                first_name varchar(50), 
                last_name varchar(50));""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
                id int auto_increment primary key,
                user_id int,
                app_date timestamp);""")
    res = cur.execute(f"SELECT first_name FROM users WHERE id = {message.from_user.id} LIMIT 1;")
    if not res.fetchone():
        sqlite_insert_user = """
                INSERT INTO users
                (id, first_name, last_name)
                VALUES (?, ?, ?);"""
        data_tuple = (message.from_user.id, message.from_user.first_name, message.from_user.last_name)
        cur.execute(sqlite_insert_user, data_tuple)
                
    conn.commit()
    cur.close()
    conn.close()

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    user_id = message.from_user.id
    rq = message.text
    ans = _process_rq(user_id, rq)
    print(message.chat.id)
    bot.send_message(message.chat.id, ans)

# bot.register_next_step_handler(message, user_name)

def get_my_bookings(user_id):
    success = 'Nothing found!'

    conn = sqlite3.connect('userbase.sql')
    cur = conn.cursor()

    res = cur.execute("SELECT * FROM appointments WHERE user_id = ?", (user_id, ))
    data = res.fetchall()

    conn.commit()
    cur.close()
    conn.close()

    if data:
        results = []
        for each in data:
            datetime_ = dateparser.parse(each[2])
            results.append(f"{{ 'date': {datetime_.date()}, 'time': {datetime_.time()}}}")
        success = '['+','.join(results)+']'
        
    return success

def book_appointment(user_id, date, time):
    success = 'Success!'

    conn = sqlite3.connect('userbase.sql')
    cur = conn.cursor()

    time_ = dateparser.parse(time).time()
    datetime_ = dateparser.parse(date).date()
    datetime_ = datetime.combine(datetime_, time_)

    data_tuple = (user_id, datetime_)
    sqlite_select_appointment = """
            SELECT COUNT(*) FROM appointments
            WHERE user_id = ? AND app_date = ?;"""
    res = cur.execute(sqlite_select_appointment, data_tuple)
    data = res.fetchone()
    print('🔺', data)
    if data[0] == 0:
        sqlite_insert_appointment = """
                INSERT INTO appointments
                (user_id, app_date)
                VALUES (?, ?);"""
        
        res = cur.execute(sqlite_insert_appointment, data_tuple)
    else:
        success = 'Failure: The time slot is not available!'

    conn.commit()
    cur.close()
    conn.close()

    return success

def cancel_appointment(user_id, date):
    
    success = 'Success!'

    conn = sqlite3.connect('userbase.sql')
    cur = conn.cursor()

    date_start = dateparser.parse(date).date()
    date_end =  (date_start + timedelta(days=1))
    
    data_tuple = (user_id, date_start, date_end)
    sqlite_select_appointment = """
            SELECT COUNT(*) FROM appointments
            WHERE user_id = ? AND app_date >= ? AND app_date <= ?;"""
    
    res = cur.execute(sqlite_select_appointment, data_tuple)
    data = res.fetchone()
    if data[0] != 0: 
        sqlite_delete_appointment = """
                DELETE FROM appointments
                WHERE user_id = ? AND app_date >= ? AND app_date <= ?;"""
        
        res = cur.execute(sqlite_delete_appointment, data_tuple)
        data = res.fetchone()
    else:
        success = 'Failure! No appointment found!'

    conn.commit()
    cur.close()
    conn.close()

    return success

def _get_user(id):
    user = users.get(id, {'id': id, 'messages': [], 'last_prompt_time': 0})
    users[id] = user
    return user

funcs = [
    {
        "name": "get_my_bookings",
        "description": "Returns a JSON array of customer's booked appointments with the barber",
        'type': 'array',
        "parameters": {
            "type": "object",
            "properties": {
            }
        }
    },
    {
        "name": "book_appointment",
        "description": "Schedule an appointment with a barber for the specified date and time. The user must provide the exact time of the appointment",
        'type': 'boolean',
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "format": "date",
                    "description": "Absolute or relative date-time in a format parseable by the Python dateparser package: dateparser.parse(...)"
                },
                "time": {
                    "type": "string",
                    "format": "time",
                    "description": "Absolute or relative date-time in a format parseable by the Python dateparser package: dateparser.parse(...)"
                }
            },
            "required": ["date", "time"]
        }
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel the barber appointment for the given date-time",
        'type': 'boolean',
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Absolute or relative date-time in a format parseable by the Python dateparser package: dateparser.parse(...)"
                }
            },
            "required": ["date"]
        }
    },
]

def _process_rq(user_id, rq):
    user = _get_user(user_id)

    # if last prompt time > 10 minutes ago - drop context
    if time.time() - user['last_prompt_time'] > 600:
        user['last_prompt_time'] = 0
        user['messages'] = []
    else:
        user['messages'] = user['messages'][-7:]

    if rq and len(rq) > 0 and len(rq) < 1000:
        user['messages'].append({"role": "user", "content": rq})
        print(user['messages'])

        msg = {'content': None}
        while not msg['content']:
            completion = openai.ChatCompletion.create(
                    model=model,
                    messages=[{'role': "system", "content": SYSTEM_MESSAGE}] + user['messages'],
                    functions=funcs,
                    temperature=0.7,
                    max_tokens=MAX_TOKENS,
                    top_p=1,
                    presence_penalty=0,
                    frequency_penalty=0,
                    stream=False
                )
            msg = completion['choices'][0]['message']
            print(msg)
            user['messages'].append(msg.to_dict())
            user['last_prompt_time'] = time.time()

            if 'function_call' in msg:
                args = json.loads(msg['function_call']['arguments'])
                print('🔥', args)
                if msg['function_call']['name'] == "get_my_bookings":
                    func_res = {"role": "function", "name": "get_my_bookings", "content": get_my_bookings(user_id)}
                elif msg['function_call']['name'] == "book_appointment":
                    func_res = {"role": "function", "name": "book_appointment", "content": book_appointment(user_id, args['date'], args['time'])}
                elif msg['function_call']['name'] == "cancel_appointment":
                    func_res = {"role": "function", "name": "cancel_appointment", "content": cancel_appointment(user_id, args['date'])}

                user['messages'].append(func_res)            
                
        return msg['content']
    else:
        user['last_prompt_time'] = 0
        user['messages'] = []
        return "!!! Error! Please use simple short texts"

bot.polling(none_stop=True)