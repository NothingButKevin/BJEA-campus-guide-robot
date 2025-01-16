from playsound import playsound

def simple_playing(filename):
    playsound("resources/audio/"+filename+".wav")

def confirm_playing(location):
    playsound("resources/audio/confirm.wav")
    playsound("resources/audio/location/"+location+".wav")

def final_playing(location):
    playsound("resources/audio/finalPt1.wav")
    playsound("resources/audio/location/"+location+".wav")
    playsound("resources/audio/finalPt2.wav")
    
if __name__ == '__main__':
    simple_playing("greeting")
    confirm_playing("8th_building")
    final_playing("11th_building")