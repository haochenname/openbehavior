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
from gpiozero import DigitalInputDevice
import RPi.GPIO as GPIO
import RatActivityCouter


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
FORWARD_LIMIT_BTN = 24
FORWARD_LIMIT_REACHED = False
# BACKWARD_LIMIT_BTN = 23
FORWARD_COUNTER = 0
touchcounter={rat0ID:0,rat1ID:0, rat2ID:0}
nextratio={rat0ID:0,rat1ID:ratio, rat2ID:ratio}
rew={rat0ID:0, rat1ID:0, rat2ID:0}
act={rat0ID:0, rat1ID:0, rat2ID:0}
ina={rat0ID:0, rat1ID:0, rat2ID:0}
# lastActiveLick={rat0ID:float(sTime), rat1ID:float(sTime), rat2ID:float(sTime)}
# lastInactiveLick={rat0ID:float(sTime), rat1ID:float(sTime), rat2ID:float(sTime)}
lastActiveLick={rat0ID:{"time":float(sTime), "scantime": 0}, rat1ID:{"time":float(sTime), "scantime":0}, rat2ID:{"time":float(sTime), "scantime":0}}
lastInactiveLick={rat0ID:{"time":float(sTime), "scantime": 0}, rat1ID:{"time":float(sTime), "scantime":0}, rat2ID:{"time":float(sTime), "scantime":0}}


##############################################################
rats = {
    rat1ID: RatActivityCouter(rat1ID,ratio , "rat1"),
    rat2ID: RatActivityCouter(rat2ID,ratio, "rat2"),
    rat0ID: RatActivityCouter(rat0ID, 0),
}

##############################################################

# FORWARD_LIMIT = DigitalInputDevice(18)
FORWARD_LIMIT = GPIO.setup(FORWARD_LIMIT_BTN, GPIO.IN, pull_up_down= GPIO.PUD_DOWN)

# BACKWARD_LIMIT = DigitalInputDevice(BACKWARD_LIMIT_BTN)


pumptimedout={rat0ID:False, rat1ID:False, rat2ID:False}
lapsed=0  # time since program start
updateTime=0 # time since last data print out 
vreinstate=0
minInterLickInterval=0.15 # minimal interlick interval (about 6-7 licks per second)
maxISI = 15  # max lapse between RFID scan and first lick in a cluster 
maxILI = 3 # max interval between licks used to turn an RFID into unknown.   

def resetPumpTimeout(rat):
    pumptimedout[rat] = False

def get_ratid_scantime(fname):
    try:
        with open(fname, "r") as f:
            (rat, scantime, dummy1, dummy1) = f.read().strip().split("\t")
            scantime = float(scantime)
    except:
        rat = "ratUnknown"
        scantime = 0

    return rat, scantime
        

while lapsed < sessionLength:
    time.sleep(0.05) # allow 20 licks per sec
    ina0 = mpr121.touched_pins[0]
    act1 = mpr121.touched_pins[1]
    lapsed = time.time() - sTime

    if GPIO.input(FORWARD_LIMIT_BTN):
        FORWARD_LIMIT_REACHED = True

    if act1 == 1:
        thisActiveLick=time.time()
        
        (ratid, scantime) = get_ratid_scantime(fname="/home/pi/_active")

        rat = rats[ratid] 
        if (thisActiveLick - rat.last_act_licks["time"] > maxILI) and (thisActiveLick - scantime > maxISI):
            rat = rats["ratUnknown"]
            
        last_act_licks = rat.last_act_licks

        if(thisActiveLick - last_act_licks["time"] > 1):
            RatActivityCouter.update_last_licks(last_act_licks, thisActiveLick, scantime)
        else:
            rat.incr_active_licks()
            if FORWARD_LIMIT_REACHED:
                dlogger.logEvent(rat, time.time(), "syringe empty", time.time() - sTime) 
            else:
                dlogger.logEvent(rat, time.time() - last_act_licks["scantime"], "ACTIVE", lapsed, rat.next_ratio) # add next ratio

            RatActivityCouter.update_last_licks(last_act_licks, thisActiveLick, scantime)
            
            RatActivityCouter.show_data(sessionLength, schedule, lapsed, \
                                        rats[rat1ID],rats[rat2ID],rats[rat0ID])

            updateTime = time.time()

        #blinkCueLED(0.2)
        if not rat.pumptimedout:
            rat.incr_touch_counter()

            if rat.touch_counter >= rat.next_ratio and rat != "ratUnknown":
                rat.incr_rewards()
                rat.reset_touch_counter()
                rat.pumptimeout = True
                # pumpTimer
                print("timeout on {}".format(rat))
                # pumpTimer.start()
                subprocess.call('python ' + './blinkenlights.py -times 1&', shell=True)

                if FORWARD_LIMIT_REACHED:
                    dlogger.logEvent(rat,time.time(), "syringe empty", time.time() - sTime)
                else:
                    dlogger.logEvent(rat, time.time()- scantime, "REWARD", time.time() - sTime)
                    mover = PumpMove()
                    mover.move("forward")
                    del(mover)

                RatActivityCouter.show_data(sessionLength, schedule, lapsed, \
                                        rats[rat1ID],rats[rat2ID],rats[rat0ID])

                updateTime = time.time()

                if schedule == "fr":
                    rat.next_ratio = ratio
                elif schedule == "vr":
                    rat.next_ratio = random.randint(1,ratio*2)
                elif schedule == "pr":
                    breakpoint += 1.0
                    rat.next_ratop = int(5*2.72**(breakpoint/5)-5)
    elif ina0 == 1:
        thisInactiveLick = time.time()

        (ratid, scantime) = get_ratid_scantime(fname="/home/pi/_inactive")

        rat = rats[ratid] 
        if (thisInactiveLick- rat.last_inact_licks["time"] > maxILI) and (thisInactiveLick - scantime > maxISI):
            rat = rats["ratUnknown"]

        last_inact_licks = rat.last_inact_licks
        if thisInactiveLick - last_inact_licks["time"] > 1:
            RatActivityCouter.update_last_licks(last_inact_licks, thisInactiveLick, scantime)
        else:
            rat.incr_inactive_licks()
            dlogger.logEvent(rat,time.time() - lastInactiveLick["scantime"], "INACTIVE", lapsed)
            RatActivityCouter.update_last_licks(last_inact_licks, thisInactiveLick, scantime)

            RatActivityCouter.show_data(sessionLength, schedule, lapsed, \
                                    rats[rat1ID],rats[rat2ID],rats[rat0ID])

            updateTime = time.time()

    # keep this here so that the PR data file will record lapse from sesion start 
    if schedule=="pr":
        lapsed = time.time() - lastActiveLick
    #show data if idle more than 1 min 
    if time.time()-updateTime > 60*1:
        RatActivityCouter.show_data(sessionLength, schedule, lapsed, \
                                rats[rat1ID],rats[rat2ID],rats[rat0ID])
        updateTime = time.time()

dlogger.logEvent("", time.time(), "SessionEnd", time.time()-sTime)

date=time.strftime("%Y-%m-%d", time.localtime())
formatted_schedule = schedule+str(ratio)+'TO'+str(timeout)+"_"+ rat1ID+"_"+rat2ID
schedule_to = schedule+str(ratio)+'TO'+str(timeout)
finallog_fname = "Soc_{}_{}_S{}_{}_summary.tab".format(date,ids.devID,ids.sesID,formatted_schedule)
data_dict = {
            "ratID1":[rat1ID, date,ids.devID,ids.sesID,schedule_to,sessionLength,act[rat1ID],ina[rat1ID],rew[rat1ID]],
            "ratID2":[rat2ID, date,ids.devID,ids.sesID,schedule_to,sessionLength,act[rat2ID],ina[rat2ID],rew[rat2ID]],
            "ratID0":[rat0ID, date,ids.devID,ids.sesID,schedule_to,sessionLength,act[rat0ID],ina[rat0ID],rew[rat0ID]]
            }
datalogger.LickLogger.finalLog(finallog_fname, data_dict)


print(str(ids.devID) +  "Session" + str(ids.sesID) + " Done!\n")
RatActivityCouter.show_data(sessionLength, schedule, lapsed, \
                        rats[rat1ID],rats[rat2ID],rats[rat0ID], "final")

subprocess.call('/home/pi/openbehavior/wifi-network/rsync.sh &', shell=True)
print(ids.devID+  "Session"+ids.sesID + " Done!\n")
