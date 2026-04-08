import robot, time
R = robot.Robot(max_motor_voltage=9)
R.servos[0].mode = robot.PWM_SERVO
R.servos[0] = -180
# Ratio: NOTE [0] IS STRONGER
motor_ratio = -0.9075 #-90.75/100
# Input time taken for robot to turn 90 degrees for power:
#R.motors[0] =-100*motor_ratio*mult, R.motors[1] =-100*mult
rotation_time=4.35
#Input time for 2.5 meters:
move=33.5
def stop():
    R.motors[0] =0
    R.motors[1] =0
def straight(back, t):
    global motor_ratio
    #back is a boolen for if it goes backward
    mult=1
    if back: mult*=-1

    R.motors[0] =-100*motor_ratio*mult
    R.motors[1] =-100*mult
    time.sleep(t)
    stop()

def turn(side_right): #ALWAYS 90 DEGREES
    global rotation_time, motor_ratio
    multi = 1
    if side_right: multi*=-1
    R.motors[0] =-90*multi*motor_ratio
    R.motors[1] = 90*multi*motor_ratio
    time.sleep(rotation_time+(2*move))
    stop()

straight(False, move)
turn(True)
straight(False, move-2)
R.servos[0] = 180
time.sleep(120-(rotation_time))
straight(True, move-2)
turn(False)
straight(True, move)





