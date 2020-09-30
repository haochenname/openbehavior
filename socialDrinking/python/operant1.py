#!/usr/bin/env python3

import pigpio
from PigpioStepperMotor import StepperMotor
import sys
import argparse
import time
from threading import Timer
import RPi.GPIO as gpio
import datalogger
import subprocess
import os
import random
import board # MPR121
import busio # MPR121
import adafruit_mpr121
import ids
from pump_move import PumpMove
import RPi.GPIO as GPIO


parser=argparse.ArgumentParser()
parser.add_argument('-schedule',  type=str, default="vr")
parser.add_argument('-ratio',  type=int, default=10)
parser.add_argument('-sessionLength',  type=int, default=3600)
parser.add_argument('-timeout',  type=int, default=20)
parser.add_argument('-rat1ID',  type=str, default="rat1")
parser.add_argument('-rat2ID',  type=str, default="rat2")
args=parser.parse_args()

# exp setting
schedule=args.schedule
ratio=args.ratio
sessionLength=args.sessionLength
timeout=args.timeout
rat1ID=args.rat1ID
rat2ID=args.rat2ID
rat0ID="ratUnknown"

## initiate pump motor
pi = pigpio.pi()

# Create I2C bus.
i2c = busio.I2C(board.SCL, board.SDA)
# Create MPR121 object.
mpr121 = adafruit_mpr121.MPR121(i2c)

# Initialize GPIO
gpio.setwarnings(False)
gpio.setmode(gpio.BCM)

# GPIO usage 
TIR = int(16) # Pin 36
SW1 = int(26) # Pin 37
SW2 = int(20) # Pin 38
TOUCHLED = int(12) #pin 32
MOTIONLED= int(6) #pin 31

# Setup switch pins
gpio.setup(SW1, gpio.IN, pull_up_down=gpio.PUD_DOWN)
gpio.setup(SW2, gpio.IN, pull_up_down=gpio.PUD_DOWN)
gpio.setup(TIR, gpio.IN, pull_up_down=gpio.PUD_DOWN)
gpio.setup(TOUCHLED, gpio.OUT)

# get date and time 
datetime=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
date=time.strftime("%Y-%m-%d", time.localtime())

# deal with session and box ID, and data file location
ids=ids.IDS()

# Initialize data logger 
dlogger = datalogger.LickLogger(ids.devID, ids.sesID)
dlogger.createDataFile(schedule+str(ratio)+'TO'+str(timeout), rat1ID+"_"+rat2ID)

# Get start time
sTime = time.time()

# GLOBAL VARIABLES
touchcounter={rat0ID:0,rat1ID:0, rat2ID:0}
nextratio={rat0ID:0,rat1ID:ratio, rat2ID:ratio}
rew={rat0ID:0, rat1ID:0, rat2ID:0}
act={rat0ID:0, rat1ID:0, rat2ID:0}
ina={rat0ID:0, rat1ID:0, rat2ID:0}
# lastActiveLick={rat0ID:float(sTime), rat1ID:float(sTime), rat2ID:float(sTime)}
# lastInactiveLick={rat0ID:float(sTime), rat1ID:float(sTime), rat2ID:float(sTime)}
lastActiveLick={rat0ID:{"time":float(sTime), "scantime": 0}, rat1ID:{"time":float(sTime), "scantime":0}, rat2ID:{"time":float(sTime), "scantime":0}}
lastInactiveLick={rat0ID:{"time":float(sTime), "scantime": 0}, rat1ID:{"time":float(sTime), "scantime":0}, rat2ID:{"time":float(sTime), "scantime":0}}

pumptimedout={rat0ID:False, rat1ID:False, rat2ID:False}
lapsed=0  # time since program start
updateTime=0 # time since last data print out 
vreinstate=0
minInterLickInterval=0.15 # minimal interlick interval (about 6-7 licks per second)
maxISI = 15  # max lapse between RFIC scan and first lick in a cluster 
maxILI = 1 # max inter lick interval in seconds  


def resetPumpTimeout(rat):
    pumptimedout[rat] = False

def showData(phase="progress"):
    if schedule=='pr':
        minsLeft=int((sessionLength-(time.time()-lastActiveLick[rat]))/60) ## need work, max of the two
    else:
        minsLeft=int((sessionLength-lapsed)/60)
    if phase=="final":
        print(ids.devID+  " Session_"+str(ids.sesID))
    print ("[" + str(minsLeft) + " min Left]")
    print (rat1ID+": Active=" + str(act[rat1ID])+" Inactive="+str(ina[rat1ID]) + " Reward=" +  str(rew[rat1ID]) + " Timeout: "+ str(pumptimedout[rat1ID]))
    print (rat2ID+": Active=" + str(act[rat2ID])+" Inactive="+str(ina[rat2ID]) + " Reward=" +  str(rew[rat2ID]) + " Timeout: "+ str(pumptimedout[rat2ID]) + "\n")
    print (rat0ID+": Active=" + str(act[rat0ID])+" Inactive="+str(ina[rat0ID]) + " Reward=" +  str(rew[rat0ID]) + " Timeout: "+ str(pumptimedout[rat0ID]) + "\n")
    return time.time()

#if (vreinstate):
#    subprocess.call('python /home/pi/openbehavior/operantLicking/python/#blinkenlights.py -times 10 &', shell=True)

def get_rat_scantime(fname, thislick, lastlick, active=True):
    try:
        with open(fname, "r") as f:
            (rat,scantime) = f.read().strip().split("\t")
            if not active:
                rat = rat[2:]
            scantime = float(scantime)
    except:
        rat="ratUnknown"
        scantime=0

    if rat is None or \
        (thislick - lastlick[rat]>maxILI and thislick - scantime > maxISI):
        rat = "ratUnknown"
    
    return rat, scantime

# prev_act_lick = 0
# prev_inact_lick = 0

while lapsed < sessionLength:
    time.sleep(0.05) # allow 20 licks per sec
    ina0 = mpr121.touched_pins[0]
    act1 = mpr121.touched_pins[1]
    lapsed = time.time() - sTime
    
    if act1 == 1:
        thisActiveLick=time.time()
        (rat, scantime)= get_rat_scantime(fname="/home/pi/_active", thislick=thisActiveLick, lastlick=lastActiveLick)

        if( lastActiveLick[rat]["time"] == float(sTime) ):
            lastActiveLick[rat]["time"] = thisActiveLick
            lastActiveLick[rat]["scantime"] = scantime
            continue

        act[rat]+=1
        dlogger.logEvent(rat,time.time() - lastActiveLick[rat]["scantime"], "ACTIVE", lapsed, nextratio[rat])
        lastActiveLick[rat]["time"]=thisActiveLick
        lastActiveLick[rat]["scantime"]=scantime

        updateTime=showData()
        #blinkCueLED(0.2)
        if not pumptimedout[rat]:
            touchcounter[rat] += 1 # for issuing rewards
            if touchcounter[rat] >= nextratio[rat]  and rat !="ratUnknown":
                rew[rat]+=1
                #print("reward for "+rat+":"+str(rew[rat]))
                dlogger.logEvent(rat, time.time()-scantime, "REWARD", time.time()-sTime)
                touchcounter[rat] = 0
                pumptimedout[rat] = True
                pumpTimer = Timer(timeout, resetPumpTimeout, [rat])
                print ("timeout on " + rat)
                pumpTimer.start()
                subprocess.call('python ' + './blinkenlights.py -times 1&', shell=True)

                mover = PumpMove()
                mover.move("forward")
                del(mover)

                updateTime=showData()
                if schedule == "fr":
                    nextratio[rat]=ratio
                elif schedule == "vr":
                    nextratio[ratio]=random.randint(1,ratio*2)
                elif schedule == "pr":
                    breakpoint+=1.0
                    nextratio[rat]=int(5*2.72**(breakpoint/5)-5)


    elif ina0 == 1:
        thisInactiveLick=time.time()
        (rat, scantime)= get_rat_scantime(fname="/home/pi/_inactive", thislick=thisInactiveLick, lastlick=lastInactiveLick, active=False)

        if( lastInactiveLick[rat]["time"] == float(sTime) ):
            lastInactiveLick[rat]["time"] = thisInactiveLick
            lastInactiveLick[rat]["scantime"] = scantime
            continue

        ina[rat]+=1
        dlogger.logEvent(rat,time.time() - lastInactiveLick[rat]["scantime"], "INACTIVE", lapsed)
        lastInactiveLick[rat]["time"]=thisInactiveLick
        lastInactiveLick[rat]["scantime"]=scantime

        updateTime=showData()
    # keep this here so that the PR data file will record lapse from sesion start 
    if schedule=="pr":
        lapsed = time.time() - lastActiveLick
    #show data if idle more than 5 min 
    if time.time()-updateTime > 60*5:
        updateTime=showData()


# signal the motion script to stop recording
#if schedule=='pr':
#    with open("/home/pi/prend", "w") as f:
#        f.write("yes")

dlogger.logEvent("", time.time(), "SessionEnd", time.time()-sTime)

print(str(ids.devID) +  "Session" + str(ids.sesID) + " Done!\n")
showData("final")

subprocess.call('/home/pi/openbehavior/wifi-network/rsync.sh &', shell=True)
print(ids.devID+  "Session"+ids.sesID + " Done!\n")
showData("final")



