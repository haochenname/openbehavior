import RPi.GPIO as gpio
import argparse
import time
import os
import sys
from time import strftime, localtime


parser=argparse.ArgumentParser()
parser.add_argument('-RatID',  type=str)
parser.add_argument('-SessionLength',  type=int)
args=parser.parse_args()

sessionLength=args.SessionLength
pirPin=35
motionLed=31

# setting up GPIO
gpio.setwarnings(False)
gpio.setmode(gpio.BOARD)
gpio.setup(pirPin, gpio.IN)        
gpio.setup(motionLed, gpio.OUT)        

## creat data files, Each box has its own ID
idfile=open("/home/pi/deviceid")
boxid=idfile.read()
boxid=boxid.strip()
startTime=time.strftime("%Y-%m-%d_%H:%M:%S", localtime())
start=time.time()
motionDataFile='/home/pi/Pies/ETOH/Motion/ETOHmotion_'+ args.RatID + '_'+ startTime + ".csv"

with open(motionDataFile,"a") as f:
	f.write("#Session Started on " +time.strftime("%Y-%m-%d\t%H:%M:%S\t", localtime())+"\n")
	f.write("RatID\tdate\tboxid\tseconds\n")
	f.close()

while time.time()-start < sessionLength:
	time.sleep(0.1)
	if gpio.input(pirPin):
		with open(motionDataFile,"a") as f:
			lapsed=time.time()-start
			f.write(args.RatID+"\t"+time.strftime("%Y-%m-%d\t", localtime()) + boxid +"\t"+ str(lapsed) +"\n")
			f.close()
		gpio.output(motionLed, True)
		time.sleep(0.1)
		gpio.output(motionLed, False)
		time.sleep(0.1)

with open(motionDataFile, "a") as f:
	f.write("#session Ended at " + time.strftime("%H:%M:%S", localtime())+"\n")
	f.close



