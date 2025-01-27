# -*- coding: utf-8 -*-

from collections import OrderedDict
from tasker_msgs.msg import *
from tasker_msgs.srv import *
import threading
import time
import subprocess
import rospy
from std_srvs.srv import Trigger, TriggerRequest
import rosnode
import rosservice

class TaskHarmoniserAgent():
    def __init__(self):

        self.switchIndicator = threading.Event()
        self.switchIndicator.clear()
        self.init_da = {'da_id': -1, 'da_name': None, 'da_type': None, 'da_state': None, 'priority': float('-inf'), 'scheduleParams': ScheduleParams()}
        self.lock = threading.Lock()
        self.queue = {}
        self.sdhl_pub = rospy.Publisher("/TH/shdl_data", ShdlDataStamped)
        self.cmd_pub = rospy.Publisher("/TH/cmd", CMD)
        self.OrderedQueue = {}
        self.execField = {}
        self.interruptField = {}
        self. sub_status = rospy.Subscriber("TH/statuses", Status, self.updateQueueData)
        self.DA_processes = {}
        self._switch_priority = None
        self.debug = False
        self.debug_file = False
    def updateQueueData(self, data):
        global th
        if self.debug ==True:
            print("\nUPDATE SP\n")
            print "updateQueueData: ",data.da_name, "state: ", data.da_state,"\nSP: \n", data.schedule_params
        if data.da_state == 'END':
            if self.queue.has_key(data.da_id):
                self.removeDA(self.queue[data.da_id])
            else:
                raise Exception('This DA: <'+data.da_name+'> is not found in THA queue')
        self.updateScheduleParams(data.da_id, data.schedule_params)
        priority = self.computePriority(data.schedule_params)
        self.updatePriority(data.da_id, priority)
        self.updateDAState(data.da_id, data.da_state)
        if self.debug ==True:
            print("\nUPDATED SP\n")

    def initialiseDA(self, executable, da_type,da_id, args):
        da_name = "DA_"+str(da_id)
        args.append( 'da_id' )
        args.append( str(da_id) )
        args.append( 'da_name' )
        args.append( da_name )
        args.append( 'da_type' )
        args.append( da_type )
        print 'args:', args
        run_cmd = [] 
        #args = ' '.join(map(str, args))
        run_cmd.append(executable)
        run_cmd.extend(args)
        package = 'multitasker'
        print "cmd: ",run_cmd
        p = subprocess.Popen(run_cmd)
        row = {'da_id': da_id, 'process': p}
        self.DA_processes[da_id] = row
        self.addDA(da_id,da_name, da_type)

    def addDA(self, added, da_name, da_type):
        # type: (int) -> None
        self.lock.acquire()        
        da = {'da_id': added, 'da_name': da_name, 'da_type': da_type, 'da_state': ["Init"], 'last_cmd_sent': None,  'priority': float('-inf'), 'ping_count': 0, 'scheduleParams': ScheduleParams()}
        self.queue[added] = da
        self.lock.release()
    def updateDA(self, da_id, da_name, da_type, da_state, priority, scheduleParams):
        # type: (int, int, ScheduleParams) -> None
        da = {'da_id': da_id, 'da_name': da_name, 'da_type': da_type, 'da_state': da_state, 'priority': priority, 'ping_count': 0, 'scheduleParams': scheduleParams}
    def updateDA(self, da):
        # type: (dict) -> None
        self.queue[da["da_id"]] = da
    def removeDA(self, da):
        self.lock.acquire()
        # type: (dict) -> None
        if self.isInterrupting():
            if self.interruptField["da_id"] == da["da_id"]:
                self.interruptField = {}
        if self.isExecuting(): 
            if self.execField["da_id"] == da["da_id"]:
                self.execField = {}
        self.queue.pop(da["da_id"], None)
        p = self.DA_processes[da["da_id"]]['process']
        # Wait until process terminates (without using p.wait())
        #
        #
        
        # while p.poll() is None:
        #     # Process hasn't exited yet, let's wait some
        #     print("TH waits for DA: "+da["da_id"]+" termination")
        #     time.sleep(0.5)
        self.lock.release()

    def removeDA_no_lock(self, da):
        # type: (dict) -> None
        if self.isInterrupting():
            if self.interruptField["da_id"] == da["da_id"]:
                self.interruptField = {}
        if self.isExecuting(): 
            if self.execField["da_id"] == da["da_id"]:
                self.execField = {}
        self.queue.pop(da["da_id"], None)
        p = self.DA_processes[da["da_id"]]['process']
        # Wait until process terminates (without using p.wait())
        #
        #

        # while p.poll() is None:
        #     # Process hasn't exited yet, let's wait some
        #     print("TH waits for DA: "+da["da_name"]+" termination")
        #     time.sleep(0.5)
    def updatePriority(self, da_id, priority):
        # type: (int, int) -> None
        self.lock.acquire()
        # print ("q: ", self.queue[da_id],"\n p: ",self.queue[da_id]["priority"], "\n new_q: ",priority)
        if self.isExecuting():
            if self.execField["da_id"] == da_id:
                self.execField["priority"] = float(priority)
                self.lock.release()
                return
        if self.isInterrupting():
            if self.interruptField["da_id"] == da_id:
                self.interruptField["priority"] = float(priority)
                self.lock.release()
                return
        if self.queue.has_key(da_id):
            self.queue[da_id]["priority"] = float(priority)
        else:
            print "[TH] - tried to update Priority of DA_",da_id," but there is no such DA" 
        # self.queue[da_id]["scheduleParams"].priority = float(priority)
        # print ("NQ: ", self.queue[da_id])
        self.lock.release()

    def computePriority(self, schedule_params):
        priority = -1* schedule_params.cost 
        return priority

    def updateScheduleParams(self, da_id, scheduleParams):
        # type: (int, ScheduleParams) -> None
        self.lock.acquire()
        if self.isExecuting():
            if self.execField["da_id"] == da_id:
                self.execField["scheduleParams"] = scheduleParams

                self.lock.release()
                return
        if self.isInterrupting():
            if self.interruptField["da_id"] == da_id:
                self.interruptField["scheduleParams"] = scheduleParams
                self.lock.release()
                return
        if self.queue.has_key(da_id):
            self.queue[da_id]["scheduleParams"] = scheduleParams
        else:
            print "[TH] - tried to update Schedule Params of DA_",da_id," but there is no such DA" 
        self.lock.release()
    def updateDAState(self, da_id, da_state):
        # type: (int, ScheduleParams) -> None
        self.lock.acquire()
        if self.isExecuting():
            if self.execField["da_id"] == da_id:
                self.execField["da_state"] = da_state
                self.lock.release()
                return
        if self.isInterrupting():
            if self.interruptField["da_id"] == da_id:
                self.interruptField["da_state"] = da_state
                self.lock.release()
                return
        if self.queue.has_key(da_id):
            self.queue[da_id]["da_state"] = da_state
        else:
            print "[TH] - tried to update STATE of DA_",da_id," but there is no such DA" 
        self.lock.release()
    def updateDALastCMD(self, da_name, cmd):
        # type: (int, ScheduleParams) -> None
        self.lock.acquire()
        if self.isExecuting():
            if self.execField["da_name"] == da_name:
                self.execField["last_cmd_sent"] = cmd
                self.lock.release()
                return
        if self.isInterrupting():
            if self.interruptField["da_name"] == da_name:
                self.interruptField["last_cmd_sent"] = cmd
                self.lock.release()
                return
        if self.queue.has_key(da_name):
            self.queue[da_name]["last_cmd_sent"] = cmd
        else:
            print "[TH] - tried to update last CMD of ",da_name," but there is no such DA" 
        self.lock.release()
    def getDALastCMD(self, da_name):
        # type: (int, ScheduleParams) -> None
        self.lock.acquire()
        if self.isExecuting():
            if self.execField["da_name"] == da_name:
                self.lock.release()
                return self.execField["last_cmd_sent"]                
        if self.isInterrupting():
            if self.interruptField["da_name"] == da_name:
                self.lock.release()
                return self.interruptField["last_cmd_sent"]
        if self.queue.has_key(da_name):
            self.lock.release()
            return self.queue[da_name]["last_cmd_sent"]
        else:
            print "[TH] - tried to get last CMD of ",da_name," but there is no such DA" 
        self.lock.release()
    def makeInterrupting(self, da_id):
        # type: (int) -> None
        if self.isInterrupting():
            self.updateDA(self.interruptField)
        self.interruptField = self.queue[da_id]
        del self.queue[da_id]
    def makeExecuting(self):
        # type: () -> None
        if self.isExecuting():
            # print "================================="
            # print "adding DA: ", self.execField
            # print "================================="
            self.updateDA(self.execField)
            # print "================================="
            # print "queue: ", self.queue
            # print "================================="
        self.execField = self.interruptField
        self.interruptField = {}
    def isInterrupting(self):
         # type: () -> bool
        return len(self.interruptField) != 0
    def isExecuting(self):
         # type: () -> bool
        return len(self.execField) != 0
    def sendIndicator(self, switch_priority):
         # type: () -> None
        self._switch_priority = switch_priority
        self.switchIndicator.set()
    def getInterruptingAndExecuting(self):
        return [self.interruptField,self.execField]
    def getQueue(self):
        queue = self.queue
        return queue
    def getNextID(self):
         # type: () -> int8
        self.lock.acquire()
        i = 0
        while True:
            for key_id in self.queue.items():
                if self.queue[key_id[0]]["da_id"] == i:
                    i = i + 1
                    # print("queue C")
                    continue
            if self.isExecuting():
                if self.execField["da_id"] == i:
                    i = i + 1
                    # print("E C")
                    continue
            if self.isInterrupting():
                if self.interruptField["da_id"] == i:
                    i = i + 1
                    # print("I C")
                    continue
            # print("break")
            break
        self.lock.release()
        return i
    def updateQueue(self, new_queue):
        # type: (OrderedDict) -> None
        self.OrderedQueue = new_queue
        # print ("NQ: ",new_queue)
        next_da = next(iter(new_queue.items()))[1]
        # print ("NDA: ", next_da)
        # print ("NDA_ID: ", next_da["da_id"])
        if not self.isExecuting():
            # print("not executing")
            self.makeInterrupting(next_da["da_id"])
            if not self.switchIndicator.isSet():
                self.sendIndicator("normal")
        else:
            # print("executing")
            if next_da["priority"] > self.execField["priority"]:
                if not self.isInterrupting():
                    if self.debug ==True:
                        print("NO INTERRUPTING DA, ", next_da["da_id"], " is interrupting now")
                    self.makeInterrupting(next_da["da_id"])
                    if not self.switchIndicator.isSet():
                        self.sendIndicator("normal")

                elif next_da["priority"] > self.interruptField["priority"]:
                    # print("da: ", next_da["da_id"],"priority: ",next_da["priority"], "\n Replaces :", self.interruptField["da_id"], "with priority: ", self.interruptField["priority"])
                    self.makeInterrupting(next_da["da_id"])
                    if not self.switchIndicator.isSet():
                        self.sendIndicator("normal")
    def updateIrrField(self, next_da, switch_priority, cost_file):
    # print ("NDA: ", next_da)
    # print ("NDA_ID: ", next_da["da_id"])
        debug = False
        if self.debug_file == True:
            cost_file.write("\n"+"IrrField:"+"\n")
            cost_file.write(str(next_da)+"\n")
        else:
            if self.debug ==True:
                print("\n"+"IrrField:"+"\n")
                print("\t Name: "+str(next_da["da_name"])+"\n")
        self.makeInterrupting(next_da["da_id"])
        if not self.switchIndicator.isSet():
            self.sendIndicator(switch_priority)
    def set_DA_signal(self, da_name, signal, data=[]):
        if self.debug ==True:
            print "set_DA_signal: "
        self.updateDALastCMD(da_name, signal)
        cmd = CMD(recipient_name = da_name, cmd = signal, data = data)
        if self.debug ==True:
            print cmd
        self.cmd_pub.publish(cmd)

    def suspendDA(self, set_exemplary_susp_task = False):
        if set_exemplary_susp_task:
            self.set_DA_signal(da_name=self.execField["da_name"], signal = "susp", data = ["rosrun", "TaskER", "exemplary_susp_task", "priority", "0"])
        else:
            self.set_DA_signal(da_name=self.execField["da_name"], signal = "susp", data = [])
        while not rospy.is_shutdown():
            wait_flag = (self.isDAAlive_with_lock(self.execField) and (self.execField["da_state"][0]!="Wait"))
            if wait_flag:
                print("Switch thread waits for exec_da to be WAIT or DEAD")
                rospy.Rate(5).sleep()
            else:
                self.lock.acquire()
                exe_da = self.execField 
                self.execField = {}
                self.lock.release()
                break
        self.lock.acquire()
        print "EXEDA: ", exe_da
        self.updateDA(exe_da)
        self.lock.release()

    def isDAAlive_no_lock(self, da):
        # print("checking DA: "+da["da_name"])
        if da["da_state"] == ['END']:
            if self.debug ==True:
                pass
                # print "THA -> DA <"+da["da_name"]+"> in END state"
            return False
        if not rosnode.rosnode_ping("/"+da["da_name"], 1):
            rospy.sleep(0.2)
            if not rosnode.rosnode_ping("/"+da["da_name"], 1):
                da["ping_count"] = da["ping_count"] + 1
            if da["ping_count"] > 4:
                # print("\n\n\nDA DEAD\n\n\n")
                return False         
        da["ping_count"] = 0       
        # print("\n\n\nDA ALIVE\n\n\n")
        return True

    def isDAAlive_with_lock(self, da):
        self.lock.acquire()
        if self.debug ==True:
            pass
            # print("checking DA: "+da["da_name"])
        if da["da_state"] == ['END']:
            if self.debug ==True:
                pass
                # print "THA -> DA <"+da["da_name"]+"> in END state"
            self.lock.release()
            return False
        if not rosnode.rosnode_ping("/"+da["da_name"], 1):
            rospy.sleep(0.2)
            if not rosnode.rosnode_ping("/"+da["da_name"], 1):
                da["ping_count"] = da["ping_count"] + 1
            if da["ping_count"] > 4:
                # print("\n\n\nDA DEAD\n\n\n")
                self.lock.release()
                return False                
        # print("\n\n\nDA ALIVE\n\n\n")
        da["ping_count"] = 0       
        self.lock.release()
        return True

    def hasService(self, srv_name):
        service_list = rosservice.get_service_list()
        if srv_name in service_list:
            if self.debug ==True:
                print("\n\n\nHAVE SERVICE\n\n\n")
            return True
        else:
            if self.debug ==True:
                print("\n\n\nLOST SERVICE\n\n\n")
            return False
    def schedule(self):

        # print("\nSCHEDULE\n")
        self.lock.acquire()
        if self.isExecuting():
            exec_da_name = "/"+self.execField["da_name"]
            # print("checking  EXEC node: ", exec_da_name)
            if not rosnode.rosnode_ping(exec_da_name, 1):
                print("FINIIIIIISSSSSHHHHHHEEEEDDDD")
                self.execField = {}
            else:
                self.execField["priority"] = self.execField["scheduleParams"].cost
        if self.isInterrupting():
            self.interruptField["priority"] = self.interruptField["scheduleParams"].cost 
            if self.isExecuting():
                self.interruptField["priority"] += self.interruptField["scheduleParams"].cost_per_sec * self.execField["scheduleParams"].completion_time
        # print (self.queue)
        for key_id in self.queue.items():
            # queued_da_name = "/"+self.queue[key_id[0]]["da_name"]

            # if not rosnode.rosnode_ping(queued_da_name, 1):
            #     print("DA terminated")
            #     del self.queue[key_id[0]]
            # else:
            self.queue[key_id[0]]["priority"] = self.queue[key_id[0]]["scheduleParams"].cost 
            if self.isExecuting():
                self.queue[key_id[0]]["priority"] += self.queue[key_id[0]]["scheduleParams"].cost_per_sec * self.execField["scheduleParams"].completion_time
        if len(self.queue) > 0:
            q = OrderedDict(sorted(self.queue.items(), 
                            key=lambda kv: kv[1]['priority'], reverse=True))
            # print ("Q: ",q)
            if self.isExecuting():
                highest_da = next(iter(q.items()))[1]
                if self.execField["priority"] < highest_da["priority"]:
                    print "WAITING FOR CONDITIONS"
                    rospy.wait_for_service('/'+self.execField["da_name"]+'/TaskER/get_suspend_conditions', timeout=2)
                    get_susp_cond = rospy.ServiceProxy('/'+self.execField["da_name"]+'/TaskER/get_suspend_conditions', SuspendConditions)
                    trig = SuspendConditionsRequest()
                    resp = get_susp_cond(highest_da["scheduleParams"].final_resource_state)
                    print "HAVE CONDITIONS"
                    self.execField["priority"] = self.execField["scheduleParams"].cost + resp.cost_per_sec*highest_da["scheduleParams"].completion_time
            self.updateQueue(q)
        ###
        #  print queue and fields
        ###
        if not self.isExecuting():
            print "No EXEC dynamic agent"
        else:
            if self.debug ==True:
                print "\nEXEC: "
                print "ID: ", self.execField["da_id"]
                print "Priority: ", self.execField["priority"]
                print "SP: \n", self.execField["scheduleParams"], "\n"
        if not self.isInterrupting():
            if self.debug ==True:
                print "No INTERRUPTING dynamic agent"
        else:
            if self.debug ==True:
                print "\tINTERRUPT: "
                print "ID: ", self.interruptField["da_id"]
                print "Priority: ", self.interruptField["priority"]
                print "SP: \n", self.interruptField["scheduleParams"], "\n"
        if self.debug ==True:
            print "\tQUEUE: "
            for key_id in self.queue.items():
                print "ID: ", self.queue[key_id[0]]["da_id"]
                print "Priority: ", self.queue[key_id[0]]["priority"]
                print "SP: \n", self.queue[key_id[0]]["scheduleParams"], "\n"

        self.lock.release()
        # print("\nSCHEDULED\n")
    def filterDA_GH(self, DA):
        if self.debug ==True:
            print "IN FILTER: ", DA
        if DA[1]["da_state"] == 'END':
            return False
        if DA[1]["da_type"] == "guide_human_tasker" and DA[1]["priority"] != float('-inf'):
            return True
        else:
            return False
    def filterDA_HF(self, DA):
        if self.debug ==True:
            print "IN FILTER: ", DA
        if DA[1]["da_state"] == 'END':
            return False
        if (DA[1]["da_type"] == "human_fell_tasker" or DA[1]["da_type"] == "human_fell_approach_tasker") and DA[1]["priority"] != float('-inf'):
            return True
        else:
            return False

    def filterDA_BJ(self, DA):
        if self.debug ==True:
            print "IN FILTER: ", DA
        if DA[1]["da_state"] == 'END':
            return False
        if DA[1]["da_type"] == "bring_jar_tasker" and DA[1]["priority"] != float('-inf'):
            return True
        else:
            return False

    def filterDA_MT(self, DA):
        if self.debug ==True:
            print "IN FILTER: ", DA
        if DA[1]["da_state"] == 'END':
            return False
        if DA[1]["da_type"] == "move_to_tasker" and DA[1]["priority"] != float('-inf'):
            return True
        else:
            return False

    def filterDA_BG(self, DA):
        if self.debug ==True:
            print "IN FILTER: ", DA
        if DA[1]["da_state"] == 'END':
            return False
        if DA[1]["da_type"] == "bring_goods_tasker" and DA[1]["priority"] != float('-inf'):
            return True
        else:
            return False

    def schedule_new(self, cost_file):
        # print("\nSCHEDULE\n")
        self.lock.acquire()
        if len(self.queue) > 0:
            ordered_queue = OrderedDict(sorted(self.queue.items(), 
                            key=lambda kv: kv[1]["priority"], reverse=True))
            if self.debug ==True:
                print "Queue before END check:\n", ordered_queue
        if self.isExecuting():
            if not self.isDAAlive_no_lock(self.execField):
                if self.debug ==True:
                    print "THA-> removes DA: ", self.execField["da_name"]
                self.removeDA_no_lock(self.execField)
        if self.isInterrupting():
            if not self.isDAAlive_no_lock(self.interruptField):
                if self.debug ==True:
                    print "THA-> removes DA: ", self.interruptField["da_name"]
                self.removeDA_no_lock(self.interruptField)
        for da in self.queue.items():
            if not self.isDAAlive_no_lock(da[1]):
                if self.debug ==True:
                    print "THA-> removes DA: ", da[1]["da_name"]
                self.removeDA_no_lock(da[1])

        # if self.isExecuting():
        #     exec_da_name = "/"+self.execField["da_name"]
        #     # print("checking  EXEC node: ", exec_da_name)
        #     if self.execField["da_state"] == 'END':
        #         self.removeDA_no_lock(self.execField)
        #         self.execField = {}
        #     if not rosnode.rosnode_ping(exec_da_name, 1):
        #         print("FINIIIIIISSSSSHHHHHHEEEEDDDD")
        #         self.execField = {}
        # if self.isInterrupting():
        #     irr_da_name = "/"+self.interruptField["da_name"]
        #     # print("checking  EXEC node: ", exec_da_name)
        #     if self.interruptField["da_state"] == 'END':
        #         self.removeDA_no_lock(self.interruptField)
        #         self.interruptField = {}
        #     if not rosnode.rosnode_ping(irr_da_name, 1):
        #         print("FINIIIIIISSSSSHHHHHHEEEEDDDD")
        #         self.interruptField = {}

        # for da in self.queue.items():
        #     if da[1]["da_state"] == 'END':
        #         self.removeDA_no_lock(da[1])
        #     if not rosnode.rosnode_ping("/"+da[1]["da_name"], 1):
        #         rospy.sleep(3)
        #         if not rosnode.rosnode_ping("/"+da[1]["da_name"], 1):
        #             print "REMOVED:"
        #             print da[1]["da_name"]
        #             self.removeDA_no_lock(da[1])
        #         print "NEXT DA"
        # print "OUT OUT"
        if len(self.queue) > 0:
            ordered_queue = OrderedDict(sorted(self.queue.items(), 
                            key=lambda kv: kv[1]["priority"], reverse=True))
            if self.debug ==True:
                print "OQ:\n", ordered_queue
            dac = next(iter(ordered_queue.items()))[1]
            DAset_GH = {}
            DAset_HF = {}
            DAset_BJ = {}
            DAset_MT = {}
            DAset_BG = {}
            cGH = {}
            cHF = {}
            cBJ = {}
            cMT = {}
            cBG = {}
            # print "Q:"
            # print self.queue
            DAset_GH = filter(self.filterDA_GH, self.queue.items())
            DAset_HF = filter(self.filterDA_HF, self.queue.items())
            DAset_BJ = filter(self.filterDA_BJ, self.queue.items())
            DAset_MT = filter(self.filterDA_MT, self.queue.items())
            DAset_BG = filter(self.filterDA_BG, self.queue.items())
            # print "DAset_GH:"
            # print DAset_GH
            # print "DAset_T:"
            # print DAset_T
            # DAset_GH = {k: v for k, v in self.queue.tems() if "tiago_guideHuman" in v[1]["da_type"]}
            # DAset_T = {k: v for k, v in self.queue.iteritems() if "tiago_transport" in v[1]["da_type"]}
            q_GH = OrderedDict(sorted(DAset_GH, 
                            key=lambda kv: kv[1]["priority"], reverse=True))
            q_HF = OrderedDict(sorted(DAset_HF, 
                            key=lambda kv: kv[1]["priority"], reverse=True))
            q_BJ = OrderedDict(sorted(DAset_BJ, 
                            key=lambda kv: kv[1]["priority"], reverse=True))
            q_MT = OrderedDict(sorted(DAset_MT, 
                            key=lambda kv: kv[1]["priority"], reverse=True))
            q_BG = OrderedDict(sorted(DAset_BG, 
                            key=lambda kv: kv[1]["priority"], reverse=True))
            if self.debug_file == True:
                cost_file.write("\n"+"Q:\n")
                cost_file.write(str(self.queue)+"\n")

            if len(DAset_HF) > 0:
                if self.debug ==True:
                    print "Have HF"
                # print "q_GH"
                # print q_GH
                cHF = next(iter(q_HF.items()))[1]
                if self.debug_file == True:
                    cost_file.write("\n"+"cHF:"+"\n")
                    cost_file.write(str(cHF)+"\n")
                dac = cHF
                if self.isExecuting():
                    if not self.filterDA_HF([None,self.execField]):
                        switch_priority = "normal"
                        self.updateIrrField(dac,switch_priority,cost_file)
                        self.lock.release()
                        return
                # print "cGH"
                # print cGH
            elif len(DAset_GH) > 0:
                if self.debug ==True:
                    print "Have GH"
                cGH = next(iter(q_GH.items()))[1]
                if self.debug_file == True:
                    cost_file.write("\n"+"cGH:"+"\n")
                    cost_file.write(str(cGH)+"\n")
                dac = cGH 
                if self.isExecuting():
                    if self.filterDA_HF([None,self.execField]):
                        self.lock.release()
                        return
                    elif not self.filterDA_GH([None,self.execField]):
                        switch_priority = "normal"
                        self.updateIrrField(dac,switch_priority,cost_file)
                        self.lock.release()
                        return    
            elif len(DAset_BJ) > 0:
                if self.debug ==True:
                    print "Have BJ"
                cBJ = next(iter(q_BJ.items()))[1]
                if self.debug_file == True:
                    cost_file.write("\n"+"cBJ:"+"\n")
                    cost_file.write(str(cBJ)+"\n")
                dac = cBJ 
                if self.isExecuting():
                    if self.filterDA_HF([None,self.execField]):
                        self.lock.release()
                        return
                    elif not self.filterDA_BJ([None,self.execField]):
                        switch_priority = "normal"
                        self.updateIrrField(dac,switch_priority,cost_file)
                        self.lock.release()
                        return    

            elif len(DAset_MT) > 0:
                if self.debug ==True:
                    print "Have MT"
                cMT = next(iter(q_MT.items()))[1]
                if self.debug_file == True:
                    cost_file.write("\n"+"cMT:"+"\n")
                    cost_file.write(str(cMT)+"\n")
                dac = cMT 
                if self.isExecuting():
                    if self.filterDA_HF([None,self.execField]):
                        self.lock.release()
                        return
                    elif not self.filterDA_MT([None,self.execField]):
                        switch_priority = "normal"
                        self.updateIrrField(dac,switch_priority,cost_file)
                        self.lock.release()
                        return    

            elif len(DAset_BG) > 0:
                if self.debug ==True:
                    print "Have BG"
                cBG = next(iter(q_BG.items()))[1]
                if self.debug_file == True:
                    cost_file.write("\n"+"cBG:"+"\n")
                    cost_file.write(str(cBG)+"\n")
                dac = cBG 
                if self.isExecuting():
                    if self.filterDA_HF([None,self.execField]):
                        self.lock.release()
                        return
                    elif not self.filterDA_BG([None,self.execField]):
                        switch_priority = "normal"
                        self.updateIrrField(dac,switch_priority,cost_file)
                        self.lock.release()
                        return    
            else:
                if self.isExecuting():
                    if not self.execField["da_type"] == dac["da_type"]:
                        print "Executing a task of a type that has higher priority" 
                        self.lock.release()
                        return 
            # if not (len(DAset_GH) > 0 or len(DAset_HF) > 0):
            #     cost_file.write("\n"+"No candidate"+"\n")
            #     print "No candidate"
            #     self.lock.release()
            #     return

            if self.debug ==True:
                print "dac: ", dac
            if self.isExecuting() and not self.isInterrupting():
                print "COMPARISION of TASKS of same type"
                if self.debug ==True:
                    print "dac priority: ", dac["priority"]
                    print "exe priority: ", self.execField["priority"]
                if dac["priority"] > self.execField["priority"]:
                    if self.debug ==True:
                        print "REQUESTING reqParam services"
                    # Exec cost for suspension behaviour and task continue starting from DAC final_resource_state -- cc_exec
                    #       , incremental (per sec) cost while waiting for start -- ccps_exec
                    while (not rospy.is_shutdown()) and not self.hasService('/'+self.execField["da_name"]+'/TaskER/get_suspend_conditions'):
                        print "Schedule thread waits for service: "+ '/'+self.execField["da_name"]+'/TaskER/get_suspend_conditions'
                        rospy.sleep(0.1)
                    rospy.wait_for_service('/'+self.execField["da_name"]+'/TaskER/get_suspend_conditions', timeout=2)
                    get_susp_cond = rospy.ServiceProxy('/'+self.execField["da_name"]+'/TaskER/get_suspend_conditions', SuspendConditions)
                    trig = SuspendConditionsRequest()
                    resp = get_susp_cond(dac["scheduleParams"].final_resource_state)
                    cc_exec = resp.cost_to_resume
                    ccps_exec = resp.cost_per_sec
                    # DAC cost while switched after EXEC finishes -- cc_dac, incremental (per sec) cost while waiting for start -- ccps_dac
            #         ccps_exec = resp.cost_per_sec
                    while (not rospy.is_shutdown()) and not self.hasService('/'+dac["da_name"]+'/TaskER/get_cost_on_conditions'):
                        print "Schedule thread waits for service: "+ '/'+dac["da_name"]+'/TaskER/get_cost_on_conditions'
                        rospy.sleep(0.1)
                    rospy.wait_for_service('/'+dac["da_name"]+'/TaskER/get_cost_on_conditions', timeout=2)
                    get_cost_cond = rospy.ServiceProxy('/'+dac["da_name"]+'/TaskER/get_cost_on_conditions', CostConditions)
                    trig = CostConditionsRequest()
                    resp = get_cost_cond(self.execField["scheduleParams"].final_resource_state)
                    cc_dac = resp.cost_to_complete
                    ccps_dac = dac["scheduleParams"].cost_per_sec
                    # Calculation of costs to switch and not switch
                    c_switch = dac["scheduleParams"].cost + cc_exec + ccps_exec * dac["scheduleParams"].completion_time 
                    c_wait = self.execField["scheduleParams"].cost + cc_dac + ccps_dac * self.execField["scheduleParams"].completion_time 
                    # send schedule data for visualisation
                    shdl_data = ShdlDataStamped()
                    shdl_data.header.stamp = rospy.Time.now()
                    shdl_data.data.dac_cost = dac["scheduleParams"].cost
                    shdl_data.data.exec_cost = self.execField["scheduleParams"].cost
                    shdl_data.data.dac_cc = cc_dac
                    shdl_data.data.exec_cc = cc_exec
                    shdl_data.data.exec_ccps = ccps_exec
                    shdl_data.data.dac_ccps = ccps_dac
                    shdl_data.data.switch_cost = c_switch
                    shdl_data.data.wait_cost = c_wait
                    shdl_data.data.dac_id = dac["da_id"]
                    shdl_data.data.exec_id = self.execField["da_id"]
                    self.sdhl_pub.publish(shdl_data)
                    print "$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$"
                    print "SHDL_DATA: "
                    print shdl_data.data
                    print "$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$"
                    if (c_switch < (c_wait - c_wait*0.1)):
                        switch_priority = "normal"
                        print "#################################################"
                        print "SWITCH"
                        print "#################################################"
                        self.updateIrrField(dac,switch_priority,cost_file)
                    else:
                        print "candidate priority was less then executing task"
                    switch_priority = "normal"
                    self.updateIrrField(dac,switch_priority,cost_file)
            #     if  (self.execField["da_type"] == "tiago_humanFell") and cHF!={}:
            #         dac = cHF
            #         if debug == True:
            #             cost_file.write("\n"+"dac:"+"\n")
            #             cost_file.write(str(dac)+"\n")
            #     elif (self.execField["da_type"] == "tiago_humanFell") and cHF=={}:
            #         print "Exec: hF, no hF in queue"
            #         if debug == True:
            #             cost_file.write("\n"+"Exec: hF, no hF in queue"+"\n")
            #     elif self.execField["da_type"] == "tiago_guideHuman":
            #         if len(DAset_HF) > 0:
            #             cost_file.write("\n"+"GH executing, there is HF in Q"+"\n")
            #             self.updateIrrField(cHF,cost_file)
            #             self.lock.release()
            #             return
            #         elif len(DAset_GH) > 0:
            #             dac = cGH
            #             if debug == True:
            #                 cost_file.write("\n"+"dac:"+"\n")
            #                 cost_file.write(str(dac)+"\n")
            #         else:
            #             cost_file.write("\n"+"No candidate"+"\n")
            #             print "No candidate"
            #     else:
            #         cost_file.write("\n"+"DA in ExecField has unknown type task"+"\n")
            #     if dac == {}:
            #         cost_file.write("\n"+"No candidate"+"\n")
            #         print "No candidate"
            #     else:
            #         cost_file.write("\n"+"Exec cost:"+"\n")
            #         cost_file.write("\t"+str(self.execField["scheduleParams"].cost)+"\n")
            #         cost_file.write("DAC cost:"+"\n")
            #         cost_file.write("\t"+str(dac["da_name"])+": "+str(dac["scheduleParams"].cost)+"\n")
            #         # if dac["scheduleParams"].cost < self.execField["scheduleParams"].cost:
            #         cost_file.write("\n"+"Have candidate"+"\n")
            #         cost_file.write("CHECK pair combinations"+"\n")
            #         print "WAITING FOR SUSPEND COST from exec"
            #         exec_da_name = "/"+self.execField["da_name"]
            #         if not rosnode.rosnode_ping(exec_da_name, 1):
            #             print("EXEC FINIIIIIISSSSSHHHHHHEEEEDDDD")
            #             self.execField = {}
            #             self.lock.release()
            #             return
            #         rospy.wait_for_service('/'+self.execField["da_name"]+'/TaskER/get_suspend_conditions')
            #         get_susp_cond = rospy.ServiceProxy('/'+self.execField["da_name"]+'/TaskER/get_suspend_conditions', SuspendConditions)
            #         trig = SuspendConditionsRequest()
            #         resp = get_susp_cond(dac["scheduleParams"].final_resource_state)
            #         cost_file.write("\n"+"EXEC:"+"\n")
            #         cc_exec = resp.cost_to_resume
            #         cost_file.write("\tcc:"+"\n")
            #         cost_file.write(str(cc_exec)+"\n")
            #         ccps_exec = resp.cost_per_sec
            #         cost_file.write("\tccps:"+"\n")
            #         cost_file.write(str(ccps_exec)+"\n")

            #         print "WAITING FOR COST from candidate"
            #         dac_name = "/"+dac["da_name"]
            #         if not rosnode.rosnode_ping(dac_name, 1):
            #             rospy.sleep(3)
            #             if not rosnode.rosnode_ping(dac_name, 1):
            #                 print "REMOVED:"
            #                 print dac["da_name"]
            #                 self.removeDA(dac)
            #                 self.lock.release()
            #                 return
            #         rospy.wait_for_service('/'+dac["da_name"]+'/TaskER/get_cost_on_conditions')
            #         get_cost_cond = rospy.ServiceProxy('/'+dac["da_name"]+'/TaskER/get_cost_on_conditions', CostConditions)
            #         trig = CostConditionsRequest()
            #         resp = get_cost_cond(self.execField["scheduleParams"].final_resource_state)
            #         cc_dac = resp.cost_to_complete
            #         cost_file.write("\n"+"DAC:"+"\n")
            #         cost_file.write("\tcc:"+"\n")
            #         cost_file.write(str(cc_dac)+"\n")
            #         ccps_dac = dac["scheduleParams"].cost_per_sec
            #         cost_file.write("\tccps:"+"\n")
            #         cost_file.write(str(ccps_dac)+"\n")
            #         cost_file.write("\n"+"COMBINATION:"+"\n")
            #         c_switch = dac["scheduleParams"].cost + cc_exec + ccps_exec * dac["scheduleParams"].completion_time 
            #         c_wait = self.execField["scheduleParams"].cost + cc_dac + ccps_dac * self.execField["scheduleParams"].completion_time 
            #         cost_file.write("\tc_switch:"+"\n")
            #         cost_file.write(str(c_switch)+"\n")
            #         cost_file.write("\tc_wait:"+"\n")
            #         cost_file.write(str(c_wait)+"\n")

            #         shdl_data = ShdlDataStamped()
            #         shdl_data.header.stamp = rospy.Time.now()
            #         shdl_data.data.dac_cost = dac["scheduleParams"].cost
            #         shdl_data.data.exec_cost = self.execField["scheduleParams"].cost
            #         shdl_data.data.dac_cc = cc_dac
            #         shdl_data.data.exec_cc = cc_exec
            #         shdl_data.data.exec_ccps = ccps_exec
            #         shdl_data.data.dac_ccps = ccps_dac
            #         shdl_data.data.switch_cost = c_switch
            #         shdl_data.data.wait_cost = c_wait
            #         shdl_data.data.dac_id = dac["da_id"]
            #         shdl_data.data.exec_id = self.execField["da_id"]
            #         self.sdhl_pub.publish(shdl_data)


            #         if (c_switch < (c_wait - c_wait*0.1)):
            #             cost_file.write("\n"+"SWITCH SWITCH SWITCH SWITCH "+"\n")
            #             self.updateIrrField(dac,cost_file)
            #         # else:
            #         #     cost_file.write("\n"+"DAC < EXEC cost:"+"\n")
            #         #     print "candidate priority was less then executing task"
            elif not self.isExecuting() and not self.isInterrupting():
                print "No EXEC, NO IRR dynamic agent"
                # if len(DAset_HF) > 0:
                #     print "HF len > 0"
                #     self.updateIrrField(cHF,cost_file)
                # elif len(DAset_GH) > 0:
                #     print "GH len > 0"
                #     self.updateIrrField(cGH,cost_file)
                if dac != None:
                    switch_priority = "normal"
                    self.updateIrrField(dac,switch_priority,cost_file)
                else:
                    print "No candidate"
            else:
                print "Processing switch"

        if not self.isExecuting():
            print "No EXEC dynamic agent"
        else:
            if self.debug ==True:
                print "\nEXEC: "
                print "ID: ", self.execField["da_id"]
                print "Cost: ", self.execField["scheduleParams"].cost
                print "SP: \n", self.execField["scheduleParams"], "\n"
        if not self.isInterrupting():
            if self.debug ==True:
                print "No INTERRUPTING dynamic agent"
        else:
            if self.debug ==True:
                print "\tINTERRUPT: "
                print "ID: ", self.interruptField["da_id"]
                print "Cost: ", self.interruptField["scheduleParams"].cost
                print "SP: \n", self.interruptField["scheduleParams"], "\n"
        if self.debug ==True:
            print "\tQUEUE: "
            for key_id in self.queue.items():
                print "ID: ", self.queue[key_id[0]]["da_id"]
                print "Cost: ", self.queue[key_id[0]]["scheduleParams"].cost
                print "SP: \n", self.queue[key_id[0]]["scheduleParams"], "\n"

        self.lock.release()
        # print("\nSCHEDULED\n")

    def switchDA(self):
        self.switchIndicator.wait()
        if self.isInterrupting():
            print("\nSWITCHING\n")
            self.lock.acquire()
            if self.isExecuting():
                commanding = self.execField
                self.lock.release()
                max_sleep_counter = 6
                sleep_counter = 0
                while self.getDALastCMD(commanding["da_name"]) in ['start','resume'] and commanding["da_state"][0] in ["Wait", "Init", "UpdateTask"]:
                    print "[Switch] -- while last cmd"
                    sleep_counter = sleep_counter + 1
                    # while commanding DA stays in ["Wait", "init", "UpdateTask"] longer then max_sleep_counter after ['start','resume'] signal,
                    # terminate the commanding DA
                    if max_sleep_counter == sleep_counter:
                        self.set_DA_signal(da_name=commanding["da_name"], signal = "terminate", data = ["priority", self._switch_priority,
                                                            #THA może zarządać odpalenia konkretnej sekwencji wstrzymania np. ("rosrun", "TaskER", "exemplary_susp_task"),
                                                            ])
                        while not rospy.is_shutdown():
                            print "[Switch] -- while sleep counter"
                            wait_flag = self.isDAAlive_with_lock(commanding)
                            if wait_flag:
                                print("Waiting for DA: ",commanding["da_name"]," to terminate after long processing of ['start','resume'] command, and new interruption is comming")
                                rospy.Rate(5).sleep()
                            else:
                                # Exec DA is terminated, remove it from Exec field
                                self.lock.acquire()
                                self.execField = {}
                                self.lock.release()
                                break
                        break
                    rospy.sleep(1)
                    
                if self.isDAAlive_with_lock(commanding):
                    print("SEND SUSPEND to commanding: ", commanding["da_id"])
                    self.set_DA_signal(da_name=commanding["da_name"], signal = "susp", data = ["priority", self._switch_priority,
                                                            #THA może zarządać odpalenia konkretnej sekwencji wstrzymania np. ("rosrun", "TaskER", "exemplary_susp_task"),
                                                            ])

                    r = rospy.Rate(5) # 10hz
                    # wait until exec DA terminates or swithes to wait state
                    while not rospy.is_shutdown():
                        wait_flag = (self.isDAAlive_with_lock(commanding) and (commanding["da_state"][0]!="Wait"))
                        if wait_flag:
                            print("Switch thread waits for exec_da to be WAIT or DEAD")
                            r.sleep()
                        else:
                            if not self.isDAAlive_with_lock(commanding):
                                # Exec DA is terminated, remove it from Exec field
                                self.lock.acquire()
                                self.execField = {}
                                self.lock.release()
                            break
            else:
                self.lock.release()
            self.lock.acquire()
            interrupting = self.interruptField
            self.lock.release()
            print("SEND StartTask to initialised: ", interrupting["da_name"])
            srv_name = "/"+interrupting["da_name"]+"/TaskER/startTask"
            # print (srv_name)
            print("\nSWITCHING: waiting for QUEUED startTask\n")
            rospy.wait_for_service(srv_name, timeout=2)
            print "\nSWITCHING: waiting for QUEUED to be in Init or Wait. It is in <", interrupting["da_state"][0], "> state."
            while not interrupting["da_state"][0] in ["Wait", "Init"]:
                if rospy.is_shutdown():
                    return 
                print "\nSWITCHING: waiting for QUEUED to be in Init or Wait. It is in <", interrupting["da_state"][0], "> state."
                rospy.sleep(0.5)

            if interrupting["da_state"][0]=="Wait":
                self.set_DA_signal(da_name=interrupting["da_name"], signal = "resume", data = [])
            elif interrupting["da_state"][0]=="Init":
                self.set_DA_signal(da_name=interrupting["da_name"], signal = "start", data = [])

            print("\nSWITCHING: waiting for STARTED hold_now\n")
            rospy.wait_for_service('/'+interrupting["da_name"]+'/TaskER/hold_now', timeout=2)
            self.lock.acquire()
            # print("\n Making executing\n")
            self.makeExecuting()
            self.switchIndicator.clear()
            # print("\n Made executing\n")
            self.lock.release()
            print("\nSWITCHED\n")
        else:
            print ("[TH] -- Killing switch thread")
        # self.isInterrupting = isInterrupting
        # self.print_log = file
        # self.handlers = {}
        # self.startState = None
        # self.endStates = []
        # self.facultativeStates = []
        # self.priority = 0
        # self.start_deadline = -1
        # node_namespace = rospy.get_name() + "/TaskER"
        # srv_name = rospy.get_name()+'/TaskER/get_hold_conditions'
        # self.s = rospy.Service(srv_name, HoldConditions, self.getHoldConditions)
        # self.current_state = ''
        # self.task_state = 0 # initialized_not_running
        # self.current_state_m_thread = 0
        # self.res_srv = None
        # self.suspend_srv = None
        # # self.sub_hold = rospy.Subscriber(node_namespace+"/hold_now", String, self.onHold)
        # # self.sub_res = rospy.Subscriber(node_namespace+"/resume_now", String, self.onResume)
        # self.q = multiprocessing.Queue()
        # self.fsm_stop_event = threading.Event()
        # self.resumeState = None
        # self.resumeData = None
        # self.pub_state = rospy.Publisher('current_state', TaskState, queue_size=10)
        # self.time_to_hold = -1 
        # self.time_to_finish = -1
        # self.onResumeData = None
    def shutdown(self):
        self.switchIndicator.set()
