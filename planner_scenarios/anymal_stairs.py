from hpp.corbaserver.rbprm.anymal import Robot
from hpp.gepetto import Viewer
from hpp.corbaserver import Client
from tools.display_tools import *
import time

from hpp.corbaserver.rbprm import  rbprmstate
from hpp.corbaserver.rbprm import  state_alg

from hpp.corbaserver.affordance.affordance import AffordanceTool

from numpy import array, zeros, ones

#~ rootJointType = 'freeflyer'
packageName = 'hpp-rbprm-corba'
meshPackageName = 'hpp-rbprm-corba'
#~ urdfName = 'hrp2_trunk_flexible'
#~ urdfNameRoms =  ['hrp2_larm_rom','hrp2_rarm_rom','hrp2_lleg_rom','hrp2_rleg_rom']
#~ urdfSuffix = ""
#~ srdfSuffix = ""

fullBody = Robot ()
fullBody.setJointBounds ("root_joint", [-20,20, -10, 10, 0, 2.2])
fullBody.client.robot.setDimensionExtraConfigSpace(0)


from hpp.corbaserver.problem_solver import ProblemSolver
ps = ProblemSolver( fullBody )
r = Viewer (ps)
v = Viewer (ps,viewerClient=r.client, displayCoM = True)



afftool = AffordanceTool ()
afftool.setAffordanceConfig('Support', [0.5, 0.03, 0.00005])
afftool.loadObstacleModel (packageName, "stair_bauzil", "planning", r)
afftool.visualiseAffordances('Support', r, [0.25, 0.5, 0.5])

# ~ fullBody.setConstrainedJointsBounds()
fullBody.setJointBounds("LF_KFE",[-1.4,0.])
fullBody.setJointBounds("RF_KFE",[-1.4,0.])
fullBody.setJointBounds("LH_KFE",[0.,1.4])
fullBody.setJointBounds("RH_KFE",[0.,1.4])
fullBody.setJointBounds ("root_joint", [-20,20, -20, 20, -20, 20])
dict_heuristic = {fullBody.rLegId:"static", fullBody.lLegId:"static", fullBody.rArmId:"fixedStep04", fullBody.lArmId:"fixedStep04"}
fullBody.loadAllLimbs(dict_heuristic,"ReferenceConfiguration",nbSamples=12)

q_ref = fullBody.referenceConfig[::]
q_init = q_ref[::] 
fullBody.setReferenceConfig(q_ref)
fullBody.setCurrentConfig (q_init)
fullBody.setPostureWeights(fullBody.postureWeights[::])

from sl1m.stand_alone_scenarios.anymal.flat_ground import solve

def getContactsFromConfig(q, limbs = Robot.limbs_names):
    s = rbprmstate.State(fullBody, q = q, limbsIncontact = limbs)
    res = {}
    for limb in limbs:
        rLegPn = s.getContactPosAndNormalsForLimb(limb)
        res[limb] = (rLegPn[0][0], rLegPn[1][0])
    return res
    # ~ rLegPn = s.getContactPosAndNormalsForLimb(Robot.rLegId)
    # ~ lLegPn = s.getContactPosAndNormalsForLimb(Robot.lLegId)
    # ~ return { Robot.rLegId : (rLegPn[0][0], rLegPn[1][0]),Robot.lLegId : (lLegPn[0][0], lLegPn[1][0]) }

#given by limb constraints
from sl1m.stand_alone_scenarios.constraints_anymal import limbNames, effectorNames
from hpp.corbaserver.rbprm.rbprmstate import StateHelper

initContacts = getContactsFromConfig(q_init)
initPos = [array(initContacts[el][0][0]) for el in limbNames]
initCom = array(fullBody.getCenterOfMass())

# ~ pb, coms, footpos, allfeetpos, res = solve(initCom = None, initPos = None)
pb, coms, footpos, allfeetpos, res = solve(initCom = initCom, initPos = initPos)

z = array([0.,0.,1.])


from scipy.optimize import linprog

#static eq is com is convex combination of pos (projected)
def staticEq(positions, com):
    sizeX = len(positions)
    E = zeros((3,sizeX))
    for i, pos in enumerate(positions):
        E[:2,i] = pos[:2]
    e = array([com[0], com[1], 1.])
    E[2,:] = ones(sizeX)
    try:
        res = linprog(ones(sizeX), A_ub=None, b_ub=None, A_eq=E, b_eq=e, bounds=[(0.,1.) for _ in range(sizeX)], method='interior-point', callback=None, options={'presolve': True})
        return res['success']
    except:
        return False

def gen_state(s, pId,  num_max_sample = 1, first = False, normal = z, newContact = True , useCom = False ):
    #~ pId = 6
    phase =  pb["phaseData"][pId]
    feetPos = allfeetpos[pId]
    sres, succ = StateHelper.cloneState(s)
    for limbId, pos in zip(limbNames, feetPos):
        sres, succ = state_alg.addNewContact(sres, limbId, pos.tolist(), normal.tolist(), num_max_sample= 200)         
        # ~ v(sres.q())   
        if not succ:
            print("succes ?", succ)
    succCom = False
    ite = 0
    # ~ #~ if first:
        # ~ #~ print "FIRST "
        # ~ #~ com[2] -= 0.25
    # ~ #~ while(not succCom and ite < 11):
    com = coms[pId*2].tolist()
    # ~ print("com ", com)
    #check whether com is feasible
    if staticEq(feetPos, com):
        print ("Config equilibrium")
        succCom = True
    if useCom:
        while(not succCom and ite < 30):
            succCom =  fullBody.projectStateToCOM(sres.sId ,com, num_max_sample)
            com[2] -= 0.05
            ite += 1    
            if succCom:
                sres2, succ = StateHelper.cloneState(sres)
                q = sres2.q()
                q[3:7] = [0.,0.,0.,1.]
                q[3:] = fullBody.referenceConfig[3:]
                sres2.setQ(q)
                succCom2 =  fullBody.projectStateToCOM(sres2.sId ,com, num_max_sample)
                if succCom2:
                    print ("SUCCESS COM2 ", succCom)
                    sres = sres2
        print ("SUCCESS COM ", succCom)
    v(sres.q())
    return sres

v(q_init)
s = rbprmstate.State(fullBody, q = q_init, limbsIncontact = limbNames[:])

states = [s]

def run():
    for i, _ in enumerate(allfeetpos[1:]):
        states.append(gen_state(states[-1],i+1, useCom = True))
        
def play():
    for s in states:
        v(s.q())
        time.sleep(0.5)
        
run()
play()
    
extraDof = [0 for _ in range(6)]
configs = [ st.q() + extraDof for st in states[:]]; i = 0