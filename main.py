from flask import Flask, render_template, request, session, redirect,url_for
from flask_socketio import join_room, leave_room, send, SocketIO, emit
import random 
import time
from threading import Thread
from string import ascii_uppercase

app = Flask(__name__)
app.config["SECRET_KEY"] = "kinjhlkjg"
socketio = SocketIO(app)

rooms = {}

words = [
    "tree",
    "airplane",
    "house",
    "car",
    "banana",
    "computer",
    "river",
    "book",
    "mountain",
    "lamp"
]

hints = [
    "Something that stands tall and changes with seasons",
    "It moves across wide open spaces above us",
    "A structure that offers shelter",
    "It helps you travel faster than walking",
    "It's curved, soft, and often found in groups",
    "A tool that connects people and ideas",
    "It flows and never stays still",
    "It holds stories and knowledge",
    "It rises high and challenges climbers",
    "It pushes back the darkness"
]

def random_word():
    index =  random.randint(0,len(words)-1)
    return words[index],hints[index]

def countdown(room):
    before_end_timer=3
    end_time=3
    while rooms.get(room) and rooms[room]["time_left"] > 0:
        socketio.sleep(1)
        rooms[room]["time_left"] -= 1
        socketio.emit("timer_update", {"time_left": rooms[room]["time_left"]}, to=room)

    socketio.send({"name": "Game", "message": "Time is up!"}, to=room)

    while before_end_timer>0:
        socketio.sleep(1)
        before_end_timer -=1

    players = rooms[room]["players"]
    highest_votes = 0
    highest_sid = None
    for sid, info in players.items():
        if info.get("votes",0) > highest_votes:
            highest_votes = info["votes"]
            highest_sid = sid
    if highest_sid is None:
        socketio.send({"name": "Game", "message": "No one was eliminated."}, to=room)
        while end_time>0:
            socketio.sleep(1)
            end_time -=1
        socketio.emit("reset_game", {}, to=room)
        return

    eliminated_name = players[highest_sid]["name"]

    if players[highest_sid].get("imposter", False):
        socketio.send({"name": "Game", "message": f"{eliminated_name} was eliminated. The impostor was found! You Win!"}, to=room)
    else:
        socketio.send({"name": "Game", "message": f"{eliminated_name} was eliminated. The impostor survives! You Lose!"}, to=room)

    while end_time>0:
        socketio.sleep(1)
        end_time -=1
    socketio.emit("reset_game", {}, to=room)
    
def generate_unique_code(length):
    while True:
        code =""
        for _ in range(length):
            code += random.choice(ascii_uppercase)

        if code not in rooms:
            break
    return code

@app.route("/", methods= ['POST','GET'])
def home():
    session.clear()
    if request.method == 'POST':
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join",False)
        create = request.form.get("create",False)

        if not name:
            return render_template("home.html", error="Please enter your name.", code=code,name=name)
        
        if join != False and not code:
            return render_template("home.html", error="Please enter a code.", code=code,name=name)

        room = code
        if create!=False:
            room = generate_unique_code(4)
            rooms[room] = {
                "members": 0,
                "messages": [],
                "players": {},
                "word": "",
                "hint": "",
                "started": False,
                "time_left": 0
            }
        
        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code,name=name)
        
        session["room"] = room
        session["name"] = name

        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
        room  = session.get("room")
        if room is None or session.get("name") is None or room not in rooms:
            return redirect(url_for("home"))
        return render_template("room.html", code=room, messages=rooms[room]["messages"])

def update_player_list(room):
    if room not in rooms:
        return
    players = rooms[room]["players"]
    emit("players_update", {
        "players": [
            {"sid": sid, "name": info["name"], "votes": info.get("votes", 0)}
            for sid, info in players.items()
        ]
    }, to=room)

@socketio.on("message")
def message(data):
    room = session.get("room")
    if room not in rooms:
        return
    content = {
        "name": session.get("name"),
        "message": data["data"]
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)

@socketio.on("vote")
def vote(data):
    room = session.get("room")
    if room not in rooms:
        return
    target_sid = data.get("target")
    players = rooms[room]["players"]
    if target_sid not in players:
        return
    
    if players[request.sid].get("voted",False):
        return
    players[request.sid]["voted"] = True
    players[target_sid]["votes"] = players[target_sid].get("votes", 0) + 1
    voter_name = players.get(request.sid, {}).get("name", "Someone")
    target_name = players[target_sid]["name"]
    send({"name": "Game", "message": f"{voter_name} voted for {target_name}."}, to=room)
    update_player_list(room)

@socketio.on("startGame")
def startGame():
    room = session.get("room")
    if room not in rooms:
        return

    if rooms[room].get("started"):
        send({"name": "Game", "message": "Game already started."}, to=room)
        return

    players = rooms[room]["players"]
    if len(players) < 3:
        send({"name": "Game", "message": "Need at least 3 players to start the game."}, to=room)
        return

    rooms[room]["started"] = True

    imposterSID = random.choice(list(players.keys()))
    word,hint = random_word()
    for sid, info in players.items():
        if sid == imposterSID:
            info["imposter"] = True
            rooms[room]["word"] = word
            send({"name": "Game", "message": "You are the imposter, don't get caught."}, to=sid)
            send({"name": "Hint", "message": hint}, to=sid)
        else:
            info["imposter"] = False
            rooms[room]["hint"] = hint
            send({"name": "Game", "message": "You are not the imposter."}, to=sid)
            send({"name": "Word", "message": word}, to=sid)

    send({"name": "Game", "message": "Game started!"}, to=room)

    emit("freeze_button",{},to=room)

    rooms[room]["time_left"] = 180
    emit("timer_update", {"time_left": rooms[room]["time_left"]}, to=room)
    socketio.start_background_task(countdown, room)


@socketio.on("reset_game")
def reset_game():
    room = session.get("room")
    if room not in rooms:
        return
    players = rooms[room]["players"]
    rooms[room]["messages"] = []
    rooms[room]["started"] = False
    emit("unfreeze_button",{},to=room)
    for sid, info in players.items():
        info["votes"] = 0
        info["voted"] = False
    update_player_list(room)

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    sid = request.sid

    if not room or not name:
        return
    
    if room not in rooms:
        leave_room(room)
        return
    
    join_room(room)

    rooms[room]["players"][sid] = {"name":name, "imposter":False, "votes":0, "voted":False}

    send({"name":name,"message":"has entered the room."}, to=room)
    rooms[room]["members"] += 1
    update_player_list(room)
    print(f"{name} has joined {room}")
    
@socketio.on("disconnect")
def disconnect(auth):
    room = session.get("room")
    name = session.get("name")
    sid = request.sid

    leave_room(room)
    if room in rooms:
        rooms[room]["players"].pop(sid, None)
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]
        else:
            update_player_list(room)

    send({"name":name,"message":"has left the room."}, to=room)
    print(f"{name} has left {room}")

if __name__ == "__main__":
    socketio.run(app, debug=True)