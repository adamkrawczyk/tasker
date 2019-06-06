#!/usr/bin/env python
import signal
import sys
from TaskHarmoniser import TaskHarmoniser
import time
import threading
import rospy 
from multitasker.srv import *
from multitasker.msg import *

_FINISH = False
scheduler = threading.Thread
switcher = threading.Thread
th = TaskHarmoniser
def updateSP(data):
	global th
	th.updatePriority(data.da_id,data.priority)
	pass
def initDA(data):
	global th
	print("GOT REQUEST")
	new_id = th.getNextID()
	print("ID: ",new_id)
	th.addDA(new_id)
	th.updatePriority(new_id, data.task_priority)
	return TaskRequestResponse(-1)

def scheduler():
	global _FINISH
	global th
	while True:
		th.schedule()
		time.sleep(1)
		if _FINISH:
			th.sendIndicator()
			break
def switcher():
	global th
	global _FINISH
	while True:
		th.switchDA()
		if _FINISH:
			break
def signal_handler(sig, frame):
	print('You pressed Ctrl+C!')
	global _FINISH
	_FINISH = True
	global scheduler
	global switcher 
	scheduler.join()   
	switcher.join() 
	sys.exit(0)

if __name__== "__main__":
	global th
	rospy.init_node('TH', anonymous=True)
	print("ready")
	signal.signal(signal.SIGINT, signal_handler)
	th = TaskHarmoniser()
	global scheduler
	global switcher
	scheduler = threading.Thread(target = scheduler)
	scheduler.start()
	switcher = threading.Thread(target = switcher)
	switcher.start()
	sub_status = rospy.Subscriber("TH/statuses", Status, updateSP)
	s = rospy.Service("TH/new_task", TaskRequest, initDA)

	rospy.spin()
  
	print("END")
    	