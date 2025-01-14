def main()
    initialization()
    while True:
        idle()
        if is_anyone_detected():
            launch_and_ask()
            if is_anyone_talking():
                run_speech_recognition()
                if result_is_meaningful():
                    repeat_the_order()
                    if is_user_comfirming_order():
                        load_the_preset_route()
                        while True:
                            if is_there_any_obstacle():
                                avoid_obstacle()
                            if is_arrived():
                                break
                    else:
                    print("Sorry, I can't understand your order.")
                else:
                print("Sorry, I can't understant your order.")
            else:
                continue
        else:
            continue

