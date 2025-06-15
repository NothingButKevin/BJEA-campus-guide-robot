import speechRecognition as sr
import keywordsMapping as km
import audioPlaying as ap

matcher = km.KeywordMatcher("resources/locationKeywords.json")

if __name__ == '__main__':
    ap.simple_playing("greeting")
    while True:
        # starts the speech recognition engine
        loc = matcher.match(sr.ASR())
        try:
            # if the location is found, play the corresponding audio
            ap.confirm_playing(loc)
            isConfirm = matcher.match(sr.ASR())
            if isConfirm == "confirm":
                break
            else:
                ap.simple_playing("misunderstoodError")
        except:
            # if the location is not found, play the default audio
            ap.simple_playing("notUnderstandError")
    ap.final_playing(loc)