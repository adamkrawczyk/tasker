
from rcprg_smach import smach_rcprg
import rospy

class TaskER(smach_rcprg.StateMachine):
    def __init__(self, da_state_name):

        smach_rcprg.StateMachine.__init__(self, da_state_name=da_state_name, outcomes=['Finished', 'shutdown'], input_keys=[], output_keys=[])
        # print "EXEC: ", self.ExeFSM(self)
        self.my_fsm = smach_rcprg.State(outcomes=['FINISHED','PREEMPTED','FAILED','shutdown'], input_keys=['goal','susp_data'])
        self.start_service = None

        with self:
            smach_rcprg.StateMachine.add('Initialise',
                                    TaskER.Initialise(self,da_state_name),
                                    transitions={'ok':'UpdateTask', 'terminate':'Cleanup'},
                                    remapping={'susp_data':'susp_data'})
            smach_rcprg.StateMachine.add('ExecFSM',
                                    self.my_fsm,
                                    transitions={'FINISHED':'Cleanup', 'PREEMPTED':'GetSuspension', 'FAILED': 'Cleanup',
                                    'shutdown':'Cleanup'},
                                    remapping={'goal':'goal', 'susp_data':'susp_data'})
            smach_rcprg.StateMachine.add('GetSuspension',
                                    TaskER.GetSuspension(self,da_state_name),
                                    transitions={'ok':'ExeSuspension'},
                                    remapping={'susp_data':'susp_data', 'fsm_es_out':'fsm_es'})
            smach_rcprg.StateMachine.add('ExeSuspension',
                                    TaskER.ExeSuspension(self,da_state_name),
                                    transitions={'FINISHED':'Wait', 'shutdown':'Cleanup'},
                                    remapping={'susp_data':'susp_data','fsm_es_in':'fsm_es'})
            smach_rcprg.StateMachine.add('Wait',
                                    TaskER.Wait(self,da_state_name),
                                    transitions={'start':'UpdateTask', 'terminate':'Cleanup'},
                                    remapping={'susp_data':'susp_data'})
            smach_rcprg.StateMachine.add('UpdateTask',
                                    TaskER.UpdateTask(self,da_state_name),
                                    transitions={'ok':'ExecFSM', 'shutdown':'Cleanup'},
                                    remapping={'susp_data':'susp_data'})
            smach_rcprg.StateMachine.add('Cleanup',
                                    TaskER.Cleanup(self, da_state_name),
                                    transitions={'ok':'Finished', 'shutdown':'shutdown'},
                                    remapping={ })
        self.debug = False
    def isDebug(self):
        return self.debug
    def swap_state(self, label, state):
        """Add a state to the opened state machine.
        
        @type label: string
        @param label: The label of the state being added.
        
        @param state: An instance of a class implementing the L{State} interface.
        
        @param transitions: A dictionary mapping state outcomes to other state
        labels or container outcomes.
        @param remapping: A dictrionary mapping local userdata keys to userdata
        keys in the container.
        """
        # Get currently opened container
        print ('Swapping state (%s, %s)' % (label, str(smach_rcprg.State)))

        # Check if th label already exists
        if label not in self._states:
            print (
            'Attempting to swap state with label "'+label+'" in state machine, but this label is not being used.')

        # Debug info
        print ("Swapping state '"+str(label)+"' to the state machine.")

        # Swap state and transitions to the dictionary
        self._states[label] = state
        return state

    def get_suspension_tf(self,susp_data):
        pass

    def exe_suspension_tf(self,fsm_es_in):
        pass
    def wait_tf(self):
        pass
    def update_task_tf(self):
        pass
    def initialise(self):
        pass
    class ExeFSM(smach_rcprg.StateMachine):
        def __init__(self, tasker_instance):
            da_state_name = "ExeFSM"
            print "RCPRG - EXE------------------------------------------------FSM"
            pass
        def reset(self):
            self.__init__(self)


    class GetSuspension(smach_rcprg.State):
        def __init__(self, tasker_instance, da_state_name):
            self.tasker_instance = tasker_instance
            da_state_name = "GetSuspension"
            smach_rcprg.State.__init__(self, outcomes=['ok'], output_keys=['fsm_es_out'])

        def execute(self, userdata):
            fsm_executable = self.tasker_instance.get_suspension_tf(userdata.susp_data)
            userdata.fsm_es_out = fsm_executable
            # userdata.susp_data.clearData()
            #srv.shutdown()
            # rospy.sleep(5)
            return 'ok'

    class BlockingState(smach_rcprg.State):
        def __init__(self, tf_freq=10, outcomes=[], input_keys=[], output_keys=[], io_keys=[]):
            self._userdata = None
            self.tf_freq = tf_freq
            input_keys.append('susp_data')
            output_keys.append('susp_data')
            self.rcprg_state = smach_rcprg.State.__init__(self, outcomes=outcomes,
                                        input_keys=input_keys,
                                        output_keys=output_keys,
                                        io_keys=io_keys)

        def execute(self, userdata):
            self._userdata = userdata
            rate = rospy.Rate(self.tf_freq)
            tf_result = None
            while tf_result is None:
                susp_flag = self.is_suspension_flag()
                try:
                    tf_result = self.transition_function(userdata)
                except Exception, e: # work on python 2.x
                    print('Failed to upload to ftp: '+ str(e))
                    tf_result='error'
                print "TF returned: ",tf_result
                if susp_flag is not None:
                    break
                rate.sleep()
            return tf_result
        def transition_function(self, userdata):
            pass

        def request_preempt(self):
            fsm_cmd = None
            if self._userdata is not None:
                data = self._userdata.susp_data.req_data
                for idx in range(0, len(data), 2):
                    if data[idx] == 'cmd':
                        fsm_cmd = data[idx+1]
                print "FSM CMD: ", fsm_cmd
                if fsm_cmd == 'susp':
                    pass
                elif fsm_cmd == 'terminate':
                    return smach_rcprg.State.request_preempt(self)
            else:
                print "Blocking state "

        def is_suspension_flag(self):
            fsm_cmd = None
            if not self._userdata == None:
                data = self._userdata.susp_data.req_data
                for idx in range(0, len(data), 2):
                    if data[idx] == 'cmd':
                        fsm_cmd = data[idx+1]
                if fsm_cmd == 'terminate':
                    return fsm_cmd
                else:
                    return None   
            else:
                return None

    class SuspendableState(smach_rcprg.State):
        def __init__(self, tf_freq=10, outcomes=[], input_keys=[], output_keys=[], io_keys=[]):
            self._userdata = None
            self.tf_freq = tf_freq
            input_keys.append('susp_data')
            output_keys.append('susp_data')
            smach_rcprg.State.__init__(self, outcomes=outcomes,
                                        input_keys=input_keys,
                                        output_keys=output_keys,
                                        io_keys=io_keys)

        def execute(self, userdata):
            self._userdata = userdata
            rate = rospy.Rate(self.tf_freq)
            tf_result = None
            while tf_result is None:
                susp_flag = self.is_suspension_flag()
                try:
                    tf_result = self.transition_function(userdata)
                except Exception, e: # work on python 2.x
                    print('Failed to upload to ftp: '+ str(e))
                print "TF returned: ",tf_result
                if susp_flag is not None:
                    break
                rate.sleep()
            return tf_result
        def transition_function(self, userdata):
            pass
        def is_suspension_flag(self):
            fsm_cmd = None
            if not self._userdata == None:
                data = self._userdata.susp_data.req_data
                for idx in range(0, len(data), 2):
                    if data[idx] == 'cmd':
                        fsm_cmd = data[idx+1]
                if fsm_cmd == 'susp' or fsm_cmd == 'terminate':
                    return fsm_cmd
                else:
                    return None   
            else:
                return None

    class ExeSuspension(smach_rcprg.State):
        def __init__(self, tasker_instance, da_state_name):
            self.tasker_instance = tasker_instance
            da_state_name = "ExeSuspension"

            smach_rcprg.State.__init__(self, outcomes=['FINISHED', 'shutdown'],input_keys=['fsm_es_in'])

        def execute(self, userdata):
            transition_name = self.tasker_instance.exe_suspension_tf(userdata.fsm_es_in)
            # or stdout, stderr = p.communicate()
            return transition_name

    class Wait(smach_rcprg.State):
        def __init__(self, tasker_instance, da_state_name):
            self.tasker_instance = tasker_instance
            da_state_name = "Wait"


            smach_rcprg.State.__init__(self, outcomes=['start', 'terminate'])

        def execute(self, userdata):
            if self.tasker_instance.isDebug() ==True:
                rospy.loginfo('{}: Executing state: {}'.format(rospy.get_name(), self.__class__.__name__))
                print 'Wait.execute'
            #srv.shutdown()
            fsm_cmd = None

            while not fsm_cmd == "resume":
                data = userdata.susp_data.getData()
                if self.tasker_instance.isDebug() ==True:
                    print "WAIT.data: ", data
                for idx in range(0, len(data), 2):
                    if self.tasker_instance.isDebug() ==True:
                        print data[idx]
                    if data[idx] == 'cmd':
                        fsm_cmd = data[idx+1]
                if self.preempt_requested() or fsm_cmd == 'terminate':
                    return 'terminate'
                # active_ros_nodes = get_node_names()
                # if not '/rico_task_harmonizer' in active_ros_nodes:
                #     return 'terminate'
                self.tasker_instance.wait_tf()
                rospy.sleep(1)
            return 'start'

    class UpdateTask(smach_rcprg.State):
        def __init__(self, tasker_instance, da_state_name):
            self.tasker_instance = tasker_instance
            da_state_name = "UpdateTask"
            smach_rcprg.State.__init__(self, outcomes=['ok', 'shutdown'])

        def execute(self, userdata):
            self.tasker_instance.update_task_tf()
            rospy.loginfo('{}: Executing state: {}'.format(rospy.get_name(), self.__class__.__name__))
            print 'UpdateTask.execute'
            #srv.shutdown()
            return 'ok'
        def is_suspension_flag(self):
            fsm_cmd = None
            if not self._userdata == None:
                data = self._userdata.susp_data.req_data
                for idx in range(0, len(data), 2):
                    if data[idx] == 'cmd':
                        fsm_cmd = data[idx+1]
                if fsm_cmd == 'susp' or fsm_cmd == 'terminate':
                    return fsm_cmd
                else:
                    return None   
            else:
                return None

    class Initialise(smach_rcprg.State):
        def __init__(self, tasker_instance, da_state_name):
            self.tasker_instance = tasker_instance
            da_state_name = "Initialise"
            smach_rcprg.State.__init__(self, outcomes=['ok', 'terminate'])

        def execute(self, userdata):
            self.tasker_instance.initialise_tf()
            fsm_cmd = None
            while not fsm_cmd == "start":
                data = userdata.susp_data.getData()
                for idx in range(0, len(data), 2):
                    print data[idx]
                    if data[idx] == 'cmd':
                        fsm_cmd = data[idx+1]
                if self.preempt_requested() or fsm_cmd == 'terminate':
                    return 'terminate'
                rospy.sleep(1)
            return 'ok'
    class Cleanup(smach_rcprg.State):
        def __init__(self, tasker_instance, da_state_name):
            self.tasker_instance = tasker_instance
            da_state_name = "Cleanup"
            smach_rcprg.State.__init__(self, outcomes=['ok', 'shutdown'])

        def execute(self, userdata):
            self.tasker_instance.cleanup_tf()
            return 'ok'