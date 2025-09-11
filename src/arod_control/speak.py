#!/usr/bin/env python3
""" Use festival to say commands """

import subprocess

# Voices for Festival TTS
VOICE_EN: str = 'voice_cmu_us_ljm_cg'
VOICE_CZ: str = 'voice_czech_krb'


def run_tts(say_bytes) -> None:
    """
         Args:Runs festival
                say_bytes: input bytes to festival
        """
    print(say_bytes)
    process = subprocess.Popen(['festival', '--pipe'], stdin=subprocess.PIPE)
    process.communicate(input=say_bytes)


def say_welcome(user_name: str = "Frederick Warwick"):
    if user_name == "Ondrej Chvala":
        say_str = '(%s) (SayText "Welcome Athena user") (%s) (SayText "Ondřej Chvála!")' % (VOICE_EN, VOICE_CZ)
        say_bytes = say_str.encode('iso-8859-2')
    else:
        say_str = '(%s) (SayText "Welcome Athena user %s!")' % (VOICE_EN, user_name)
        say_bytes = say_str.encode('utf-8')
    run_tts(say_bytes)


def say_motor_stop():
    run_tts(('(%s) (SayText "Drive motor stop!")' % VOICE_EN).encode('utf-8'))


def say_motor_up():
    run_tts(('(%s) (SayText "Drive motor up!")' % VOICE_EN).encode('utf-8'))


def say_motor_down():
    run_tts(('(%s) (SayText "Drive motor down!")' % VOICE_EN).encode('utf-8'))


def servo_engage():
    run_tts(('(%s) (SayText "Engaging the drive!")' % VOICE_EN).encode('utf-8'))


def servo_scram():
    run_tts(('(%s) (SayText "Scramming the reactor!")' % VOICE_EN).encode('utf-8'))


def source_in():
    run_tts(('(%s) (SayText "Neutron source inserted!")' % VOICE_EN).encode('utf-8'))


def source_out():
    run_tts(('(%s) (SayText "Neutron source removed!")' % VOICE_EN).encode('utf-8'))


if __name__ == '__main__':
    say_welcome()
