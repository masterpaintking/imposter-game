
def count_down():
    time_in_seconds = 180
    minutes = time_in_seconds/60
    seconds = time_in_seconds%60
    print(f"{int(minutes)}:{seconds}")

count_down()