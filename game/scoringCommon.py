# AIX2 Reality coop
# Original script from AIX team
# Rework by MaxP

import players
players.init()
import math

import game.common
import game.players
import string

import host
import bf2
from bf2.stats.constants import *
from bf2 import g_debug
import game.maplist
from game.bf2object import bf2object
import sys
import math
from game.timer import timer, loop
if sys.platform == 'win32':
	import ntpath as path
elif sys.platform == 'unknown':
	import posixpath as path
#g_debug = True

SCORE_KILL = 2
SCORE_TEAMKILL = -10
SCORE_SUICIDE = -2
SCORE_REVIVE = 3
SCORE_TEAMDAMAGE = -2
SCORE_TEAMVEHICLEDAMAGE = -2
SCORE_DESTROYREMOTECONTROLLED = 2
SCORE_KILLASSIST_DRIVER = 1
SCORE_KILLASSIST_PASSENGER = 0
SCORE_KILLASSIST_TARGETER = 1
SCORE_KILLASSIST_DAMAGE = 1

REPAIR_POINT_LIMIT = 500
HEAL_POINT_LIMIT = 500
GIVEAMMO_POINT_LIMIT = 500
TEAMDAMAGE_POINT_LIMIT = 500
TEAMVEHICLEDAMAGE_POINT_LIMIT = 500

REPLENISH_POINT_MIN_INTERVAL = 30	# seconds
VEHICLE_TYPES = {"0":"armoured vehicle", "1":"plane", "2":"air defence", "3":"helicopter", "4":"transport vehicle", "5":"artillery", "6":"ground defence", "7":"parachute (WTF?)", "8":"soldier", "11":"vehicle"}


# sub score
NORMAL = 0
SKILL = 1
RPL = 2
CMND = 3


VEHICLE_BONUS_CONF_FILE = "mods/aix2_reality/python/game/vehicle_bonus.conf"
g_vehicle_bonus = dict()
VEHICLE_TKBONUS_CONF_FILE = "mods/aix2_reality/python/game/vehicle_tkbonus.conf"
g_vehicle_tkbonus = dict() 
g_delay = False
mine_delay = False

def init():
	global g_vehicle_bonus

	fread = open(VEHICLE_BONUS_CONF_FILE)
	readlines = fread.readlines()
	fread.close()
	
	for line in readlines:
	    list = line.split(',')
	    if len(list) > 1:
	        g_vehicle_bonus[list[0]] = list[1]
	
	global g_vehicle_tkbonus

	fread = open(VEHICLE_TKBONUS_CONF_FILE)
	readlines = fread.readlines()
	fread.close()
	
	for line in readlines:
	    list = line.split(',')
	    if len(list) > 1:
	        g_vehicle_tkbonus[list[0]] = list[1]


	# set limits for how many repair HPs etc are needed to get a callback
	bf2.gameLogic.setHealPointLimit(HEAL_POINT_LIMIT)
	bf2.gameLogic.setRepairPointLimit(REPAIR_POINT_LIMIT)
	bf2.gameLogic.setGiveAmmoPointLimit(GIVEAMMO_POINT_LIMIT)
	bf2.gameLogic.setTeamDamagePointLimit(TEAMDAMAGE_POINT_LIMIT)
	bf2.gameLogic.setTeamVehicleDamagePointLimit(TEAMVEHICLEDAMAGE_POINT_LIMIT)
	
	host.rcon_invoke("sv.numPlayersNeededToStart 1")
	host.registerGameStatusHandler(onGameStatusChanged)
	
	if g_debug: print("scoring common init")



def onGameStatusChanged(status):
	if status == bf2.GameStatus.Playing:
		host.registerHandler('PlayerSpawn', onPlayerSpawn)
		host.registerHandler('PlayerKilled', onPlayerKilled)
		host.registerHandler('PlayerDeath', onPlayerDeath)
		host.registerHandler('PlayerRevived', onPlayerRevived)
		host.registerHandler('PlayerHealPoint', onPlayerHealPoint)
		host.registerHandler('PlayerRepairPoint', onPlayerRepairPoint)
		host.registerHandler('PlayerGiveAmmoPoint', onPlayerGiveAmmoPoint)
		host.registerHandler('PlayerTeamDamagePoint', onPlayerTeamDamagePoint)
		host.registerHandler('VehicleDestroyed', onVehicleDestroyed)
		host.registerHandler('PickupKit', onPickup)
		host.registerHandler('DropKit', onDropKit)
		host.registerHandler('EnterVehicle', onEnterVehicle)

	elif status == bf2.GameStatus.EndGame:
		giveCommanderEndScore(bf2.playerManager.getCommander(1), bf2.gameLogic.getWinner())
		giveCommanderEndScore(bf2.playerManager.getCommander(2), bf2.gameLogic.getWinner())
		for player in bf2.playerManager.getPlayers():
			if not player.isAIPlayer():
				setattr(player, 'cheats', [])
			setattr(player, 'already_issued', (None, None, None, False))


def createdata(victim, attacker, weapon):
	attackername = None
	attackerposition = None
	victimname = None
	victimposition = None
	victimspeed = None
	try:
		attackername = attacker.getName()
		attackerposition = game.players.getposition(attacker)
		victimname = victim.getName()
		victimposition = game.players.getposition(victim)
		victimspeed = game.players.getspeed(victim)

		if weapon:
			scoringtype = getWeaponType(weapon.templateName)

		if scoringtype != 4:
			return

		data = [attacker,
				attackername,
				attackerposition,
				victim,
				victimname,
				victimposition,
				victimspeed,
				scoringtype]
		
		return data
	except:
		game.common.print_exception()


def delayedplayerkilled(data):
	try:
		attacker = data[0]
		attackername = data[1]
		attackerposition = data[2]
		victim = data[3]
		victimname = data[4]
		victimposition = data[5]
		victimspeed = data[6]
		scoringtype = data[7]
		speedscore = 0
		finalscore = 0
		distance = game.common.vectordistance(attackerposition, victimposition)
	
		if victimspeed:
			if victimspeed > 5:
				speedtext = "running"
				speedscore = (2,3)[distance > 100]
			elif victimspeed > 1:
				speedtext = "walking"
				speedscore = (1,2)[distance > 100]
			else:
				speedtext = "stationary"
				speedscore = 0
		else:
			speedtext = "stationary"
			speedscore = 0

		if attackerposition and victimposition and distance > 150:
			finalscore = round(distance / 150) + speedscore

		if finalscore > 0:
			if victim.isSquadLeader():
				finalscore += 5
			addScore(attacker, finalscore, SKILL)

		if finalscore > 0 and distance > 10:
			message = (str(speedtext) + " target [+", "enemy squad leader [+")[victim.isSquadLeader()]
			killmessage = str(attackername) + " got a " + str(int(distance)) + "m sniper shot on a " + message + str(int(finalscore)) + "]"
			game.common.sayall(killmessage)

	except:
		game.common.print_exception()


# give commander score for every player score
def addScore(player, points, subScore=NORMAL, subPoints=-1):

	player.score.score += points
	if subPoints == -1:
		subPoints = points
	
	# sub score
	if subScore == RPL:
		player.score.rplScore += subPoints
	if subScore == SKILL:
		player.score.skillScore += subPoints
	if subScore == CMND:
		player.score.cmdScore += subPoints


def onEnterVehicle(player, vehicle, freeSoldier = False):
	if g_debug: print(str(player.getname()) + " enter the " + str(vehicle.templateName))
	if not player.isAIPlayer() and not freeSoldier:
		vehicletype = vehicle.templateName

		if "ighlander" in player.getName() and (getVehicleType(vehicletype)) == 1:
			for p in bf2.playerManager.getPlayers():
				if not p.isAIPlayer() and not "ighlander" in p.getName():
					text = ('Tigran in a plane! ALARM! ACHTUNG!')
					for ln in text.splitlines():
						host.sgl_sendTextMessage(p.index, 14, 1, ln.rstrip(), 0)
		if (vehicle.templateName).lower() == "rutnk_t90a":
			message = ('You can activate the "Arena" APS system by pressing 6 key --> LMB')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)
			message = ('Special ballistic mode for frag projectiles is available at index 7')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)

		elif (vehicle.templateName).lower() == "sf14_periscope":
			message = ('You can call a mortar barrage with the periscope')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)

		elif (vehicle.templateName).lower() in ["ru_aav_tunguska","ger_aav_fennekswp","nl_aav_fennekswp","bf4_tunguska"]:
			message = ('You can switch between SACLOS/SAM missile guidance by pressing the weapon selection key (F)')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)
		elif (vehicle.templateName).lower() in ["us_jet_harrier","gb_jet_harrier","us_jet_f35a","aix_yak38"]:
			message = ('This aircraft can do a VTOL: press "S" key for take off')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)
		elif (vehicle.templateName).lower() == "us_jet_a10a_sp":
			message = ('Press 4 key to enter gunpod mode. Press "C" in the gunpod mode to zoom')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)
		elif (vehicle.templateName).lower() == "rah66a":
			message = ('You can switch between LG and AA missiles by pressing the weapon selection button (F)')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)
		elif (vehicle.templateName).lower() == "usaav_m6":
			message = ('You can switch between Stinger missiles and coaxial mg by pressing the weapon selection button (F)')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)
		elif (vehicle.templateName).lower() == "mosquitoair":
			message = ('You can drop AP mine with RMB')
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)
		elif (vehicle.templateName).lower() == "ruair_su24":
			message = ("This plane is equipped with very powerful bombs")
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)
		elif (vehicle.templateName).lower() == "ger_jet_tornadogr4_mw1":
			message = ("This plane is equipped with antipersonnel mines - MIFF")
			for ln in message.splitlines():
				host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)


def giveCommanderEndScore(player, winningTeam):
	if player == None: return
	if player.getTeam() != winningTeam: return


def onPlayerKilledKit(victim, attacker, weapon, assists, object):
	kit = victim.getKit()
	if str(kit.templateName) in ["Assault_nsv","Assault_666","Assault_777"]:
#		setattr(victim, 'handler_registered', False)
		message = (str(victim.getName()) + " lost his wunderwaffe again...")
		for p in bf2.playerManager.getPlayers() and p.getName() != victim.getName():
			if not p.isAIPlayer():
				for ln in message.splitlines():
					host.sgl_sendTextMessage(p.index, 14, 1, ln.rstrip(), 0)


def onDropKit(player, kit):
	if not player.isAIPlayer():
		if str(kit.templateName) in ["Assault_nsv","Assault_666","Assault_777"]:
			player.getDefaultVehicle().setDamage(200)
			monitor, cursed = getattr(player, 'health_monitor', [None, True])
			setattr(player, 'health_monitor', [monitor, False])


def onPickup(player, kit):
	global cursed_loop
	if g_debug: print(str(player.getname()) + " picked up an " + str(kit.templateName))
	if not player.isAIPlayer():
		if str(kit.templateName) in ["Assault_nsv","Assault_666","Assault_777"]:
			game.common.sayall(str(player.getName()) + " has found a secret weapon kit. Who knows what this will lead to...")
			body = player.getDefaultVehicle()
			vehicle = bf2.objectManager.getRootParent(body)
			health = body.getDamage()
			body.setDamage(body.getDamage() - 50)
			monitor, cursed = getattr(player, 'health_monitor', [None, False])
			setattr(player, 'health_monitor', [monitor, True])


def onPlayerSpawn(player, soldier):
	global g_vehicle_bonus
	if "boat_rib_hmg_m3" in g_vehicle_bonus:
		player.hasreadinstruction = True


def vehicle_type(name):
	return(VEHICLE_TYPES.get(str(getVehicleType(name)), "vehicle"))


def timerHandler(params):
	player, only_message = params
	victimVehicle, VehicleName, victim, teamkill = getattr(player, 'already_issued', (None, None, None, False))
	if only_message:
		if str(VehicleName).lower() in ["tony_goliath"]:
			game.common.sayall(str(player.getName()) + " destroyed an enemy unmanned vehicle")
		elif str(VehicleName).lower() not in ["suicide_drone_uav"]:
			game.common.sayall(str(player.getName()) + " destroyed an enemy " + str(vehicle_type(VehicleName)))
		return

	if not victimVehicle or victimVehicle.getIsWreck() or victimVehicle.getDamage() <= 0:
		if not teamkill:
			addScore(player, int(g_vehicle_bonus[str(VehicleName).lower()]), SKILL)
			if not player.isAIPlayer():
				if str(VehicleName).lower() in ["tony_goliath"]:
					game.common.sayall(str(player.getName()) + " destroyed an enemy unmanned vehicle [+" + str(SCORE_KILL + int(g_vehicle_bonus[str(VehicleName).lower()])) + "]")
				elif str(VehicleName).lower() not in ["suicide_drone_uav"]:
					game.common.sayall(str(player.getName()) + " destroyed an enemy " + str(vehicle_type(VehicleName)) + " [+" + str(SCORE_KILL + int(g_vehicle_bonus[str(VehicleName).lower()])) + "]")

		else:
			score_value = int(g_vehicle_tkbonus[str(VehicleName).lower()])
			if not victim.isAIPlayer() and not player.isAIPlayer():
				score_value += score_value
				if victim_dict.get(player.getName(), 0) > 0:
					score_value = victim_dict[player.getName()] + score_value
					if score_value < 0:
						addScore(player, score_value + 2, RPL)
						score_value = 0
					message = ("Eye for an eye, " + str(victim.getName()))
					victim_dict[player.getName()] = score_value
		
				elif overall > 0:
					overall = overall + score_value
					if overall < 0: 
						overall = 0
					victim_dict['overall'] = overall
					addScore(player, 2, RPL)
					return
				
				else:
					killer_dict[victim.getName()] = killer_dict.get(victim.getName(), 0) - score_value
					overall = overall - score_value
					killer_dict['overall'] = killer_dict.get('overall', 0) - score_value

			addScore(victim, -score_value, RPL)
			addScore(player, score_value, RPL)
			game.common.sayall(str(player.getName()) + " destroyed a friendly vehicle [" + str(SCORE_TEAMKILL + score_value) + "]")

	setattr(player, 'already_issued', (None, None, None, False))


def mineCheckHandler(count_mines):
	global mine_delay
	if not mine_delay:
		print(host.timer_getWallTime(), "mineCheckHandler")
		mine_delay = True
		count_mines = 0
		mines = bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.GenericProjectile')
		for mine in mines:
			if str(mine.templateName).lower() in ["usmin_claymore_projectile","ger_jet_tornadogr4_w_miff_projectile","vnhgr_betty_projectile","tm62m_mine_projectile","rumin_mon50_projectile","chmin_type66_projectile","at_mine_projectile","insgr_hgr_trap_projectile","arty_ied_projectile","c4_slam_projectile","bm21_mines"]:
				count_mines += 1
		if count_mines > 900:
			message = ('\xa73\xa7c1001' + 'Warning, there are ' + str(count_mines) + ' mines in game!' + '\xa73\xa7c1001')
			game.common.sayall(message)

		count_rally = 0
		for rally in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.PlayerControlObject'):
			if (str(rally.templateName).lower())[0:15] == "rallypoint_hand" and rally.getPosition() != (0.0,0.0,0.0):
				count_rally += 1
				if count_rally > 6:
					out = getObjectsOfTemplate(rally.templateName)
					try_destruct_vehicle(out[-1][0], out[-1][1])
	
		bf2.Timer(mineCheckHandler_delay, 30, 1, 0)


def mineCheckHandler_delay(delay):
	global mine_delay
	mine_delay = False


def activeObject(id):
	rconExec('object.active id%d' % int(id))


def listObjectsOfTemplate(template):
	out = rconExec('object.listObjectsOfTemplate ' + template)
	if out:
		return [ x.split()[3] for x in out.split('\n') ]
	return []


def getObjectsOfTemplate(template_name):
	ids = listObjectsOfTemplate(template_name)
	if ids:
		return zip(bf2.objectManager.getObjectsOfTemplate(template_name), ids)
	else:
		return ids


def deleteObject(id):
	activeObject(id)
	rconExec('object.delete')


def try_destruct_vehicle(vehicle, vehicle_id):
#	bf2.Timer(lambda x: deleteObject(x), 2, 1, vehicle_id)
	vehicle.setDamage(0)
	deleteObject(vehicle_id)

def onPlayerKilled(victim, attacker, weapon, assists, object):
	killedByEmptyVehicle = False
	countAssists = False

	if "ighlander" in attacker.getName() and "Glorius LowPassFilter" in victim.getName():
		game.common.sayall('Tigran killed Glorius LowPassFilter again')	

	# killed by unknown, no score
	if attacker == None:
		
		# check if killed by vehicle in motion
		if weapon == None and object != None:
			if hasattr(object, 'lastDrivingPlayerIndex'):
				attacker = bf2.playerManager.getPlayerByIndex(object.lastDrivingPlayerIndex)
				killedByEmptyVehicle = True


		if attacker == None:
			if g_debug: print("No attacker found")
			pass

			victimVehicle = bf2.objectManager.getRootParent(victim.getVehicle())
	# killed by remote controlled vehicle, no score awarded in this game
#	if object and object.isPlayerControlObject and object.getIsRemoteControlled():		
#		pass
		
	# no attacker, killed by object
	if attacker == None:
		pass
		
	# killed by self
	elif attacker == victim:

		# no suicides from own wreck
		if killedByEmptyVehicle and object.getIsWreck():
			return

		attacker.score.suicides += 1
		if not attacker.isAIPlayer():
			addScore(attacker, SCORE_SUICIDE, RPL)
		
	# killed by own team
	elif attacker.getTeam() == victim.getTeam():
		killer_dict = getattr(attacker, 'killer_dict', None)
		victim_dict = getattr(victim, 'killer_dict', None)
		if not killer_dict:
			killer_dict = dict()
		if not victim_dict:
			victim_dict = dict()
		overall = victim_dict.get('overall', 0)
		message = None
		vehicle = victim.getVehicle()
		victimVehicle = bf2.objectManager.getRootParent(vehicle)
		VehicleTKName = victimVehicle.templateName
		if (not getattr(attacker, 'already_issued', (None, None, None, False))[0] == victimVehicle 
			and str(VehicleTKName).lower() in g_vehicle_tkbonus 
			and not str(VehicleTKName).lower() in ["suicide_drone_uav","fsa_tnk_bomber","civ_jep_support_bomber","civ_jep_car_bomber","civ_jep_car_bomber_black","civ_jep_car_bomber_blue","civ_jep_car_bomber_white","mil_trk_logistics_bomber","fsa_jep_zastava900ak_logistics_bomber"]):
			setattr(attacker, 'already_issued', (victimVehicle, VehicleTKName, victim, True))
			bf2.Timer(timerHandler, 1, 1, (attacker, False))
		#return

		# no teamkills from wrecks
		if object != None and object.getIsWreck():
			return
			
		# no teamkills from artillery
		if weapon:
			attackerVehicle = bf2.objectManager.getRootParent(weapon)
			if attackerVehicle.isPlayerControlObject and attackerVehicle.getIsRemoteControlled():
				return

		if weapon == None and object != None:
			victimVehicle = victim.getVehicle()
			victimRootVehicle = bf2.objectManager.getRootParent(victimVehicle)
			victimVehicleType = getVehicleType(victimRootVehicle.templateName)
			attackerVehicle = attacker.getVehicle()
			attackerRootVehicle = bf2.objectManager.getRootParent(attackerVehicle)
			attackerVehicleType = getVehicleType(attackerRootVehicle.templateName)
			if attackerVehicleType == 1 and victimVehicleType == 8:
				return

		attacker.score.TKs += 1
		score = SCORE_TEAMKILL

		if not attacker.isAIPlayer(): #not victim.isAIPlayer() and
			score = SCORE_TEAMKILL * 2

			if victim_dict.get(attacker.getName(), 0) > 0:
				score = victim_dict.get(attacker.getName(), 0) + score
				if score < 0:
					addScore(attacker, score + 2, RPL)
					score = 0
				message = ("Eye for an eye, " + str(victim.getName()))
				victim_dict.update({str(attacker.getName()) : score})
	
			elif overall > 0:
				overall = overall + score
				if overall < 0: 
					overall = 0
				victim_dict.update({'overall' : overall})
				addScore(attacker, 2, RPL)
#				return
			
			else:
				killer_dict.update({str(victim.getName()): killer_dict.get(victim.getName(), 0) - score})
				overall = overall - score
	
			killer_dict.update({'overall' : killer_dict.get('overall', 0) - score})
			setattr(attacker, 'killer_dict', killer_dict)
			setattr(victim, 'killer_dict', victim_dict)
		if score != 0:
			addScore(attacker, (score + 2), RPL)
			addScore(victim, 4, RPL)
		countAssists = True
#		if not attacker.isAIPlayer():
#			game.common.sayall(str(killer_dict.items()))
		if message:
			game.common.sayall(message)

	# killed by enemy
	else:
		if weapon.templateName in ["aix_portableminigun","aix_portableminigun_mec"]:
			body = attacker.getDefaultVehicle()
			currentdamage = body.getDamage()
			body.setDamage(currentdamage + 25)

		if attacker.score.rplScore > -50:
			attacker.score.kills += 1
			finalscore = (SCORE_KILL, int(round(SCORE_KILL * min(2,(1 + attacker.score.rplScore/30)))))[attacker.score.rplScore > 10]
			addScore(attacker, finalscore, SKILL)
		vehicle = victim.getVehicle()
		victimVehicle = bf2.objectManager.getRootParent(vehicle)
		VehicleName = victimVehicle.templateName
		if not getattr(attacker, 'already_issued', (None, None, None, False, False))[0] == victimVehicle and str(VehicleName).lower() in g_vehicle_bonus:
			setattr(attacker, 'already_issued', (victimVehicle, VehicleName, victim, False))
			if attacker.score.rplScore >= 2:
				bf2.Timer(timerHandler, 1, 1, (attacker, False))
			else:
				if not attacker.isAIPlayer():
					bf2.Timer(timerHandler, 1, 1, (attacker, True))

		#Sniper bonuses
		if not attacker.isAIPlayer() and getVehicleType(attacker.getVehicle().templateName) == 8 and attacker and victim and weapon:
			if weapon:
				scoringtype = getWeaponType(weapon.templateName)
			if scoringtype == 4:
				data = createdata(victim, attacker, weapon)
				bf2.Timer(delayedplayerkilled, 0.1, 1, data)
		countAssists = True


	# kill assist
	if countAssists and victim:

		for a in assists:
			assister = a[0]
			assistType = a[1]
			
			if assister.getTeam() != victim.getTeam():
			
				# passenger
				if assistType == 0:
					assister.score.passengerAssists += 1
					addScore(assister, SCORE_KILLASSIST_PASSENGER, RPL)
				# targeter
				elif assistType == 1:
					assister.score.targetAssists += 1
					addScore(assister, SCORE_KILLASSIST_TARGETER, RPL)
				# damage
				elif assistType == 2:
					assister.score.damageAssists += 1
					addScore(assister, SCORE_KILLASSIST_DAMAGE, RPL)
				# driver passenger
				elif assistType == 3:
					assister.score.driverAssists += 1
					addScore(assister, SCORE_KILLASSIST_DRIVER, RPL)
				else:
					# unknown kill type
					pass
			

def onPlayerDeath(victim, vehicle):
#	pass
	global mine_delay
	if not mine_delay:
		bf2.Timer(mineCheckHandler, 1, 1, 0)


def onPlayerRevived(victim, attacker):
	if attacker == None or victim == None or attacker.getTeam() != victim.getTeam():
		return

	attacker.score.revives += 1
	addScore(attacker, SCORE_REVIVE * (1 + int(victim.isAIPlayer())), RPL)
	bf2.gameLogic.sendGameEvent(attacker, 10, 4) #10 = Replenish, 4 = Revive


# prevent point-exploiting by replenishing same player again
def checkGrindBlock(player, object):

	if object.isPlayerControlObject:
		defPlayers = object.getOccupyingPlayers()
		if len(defPlayers) > 0:
			defPlayer = defPlayers[0]
			
			if not hasattr(player, 'lastReplenishPointMap'):
				player.lastReplenishPointMap = {}
			else:	
				if defPlayer.index in player.lastReplenishPointMap:
					if player.lastReplenishPointMap[defPlayer.index] + REPLENISH_POINT_MIN_INTERVAL > host.timer_getWallTime():
						return True
					
			player.lastReplenishPointMap[defPlayer.index] = host.timer_getWallTime()

	return False


def onPlayerHealPoint(player, object):
	if checkGrindBlock(player, object):
		return

	player.score.heals += 1
	addScore(player, 1, RPL)
	bf2.gameLogic.sendGameEvent(player, 10, 0) 	# 10 = Replenish, 0 = Heal
	
	giveDriverSpecialPoint(player)
	
	

def onPlayerRepairPoint(player, object):
	if checkGrindBlock(player, object):
		return
	
	player.score.repairs += 1
	addScore(player, 2, RPL)
	bf2.gameLogic.sendGameEvent(player, 10, 1) 	# 10 = Replenish, 1 = Repair
	
	giveDriverSpecialPoint(player)



def onPlayerGiveAmmoPoint(player, object):
	if checkGrindBlock(player, object):
		return
	
	player.score.ammos += 1
	addScore(player, 2, RPL)
	bf2.gameLogic.sendGameEvent(player, 10, 2) 	# 10 = Replenish, 2 = Ammo

	giveDriverSpecialPoint(player)



def giveDriverSpecialPoint(player):

	# special point given to driver, if someone in vehicle gets an abilitypoint
	vehicle = player.getVehicle()
	if vehicle:
		rootVehicle = bf2.objectManager.getRootParent(vehicle)
		plrs = rootVehicle.getOccupyingPlayers()
		# Protect against empty tuple, which seems to occur.
		if len(plrs) == 0: return
		driver = plrs[0]
	
		if driver != None and driver != player and driver.getVehicle() == rootVehicle:
			driver.score.driverSpecials += 1
			addScore(driver, 1, RPL)
			bf2.gameLogic.sendGameEvent(driver, 10, 3) #10 = Replenish, 3 = DriverAbility

	
	
def onPlayerTeamDamagePoint(player, object):
	vehicleType = getVehicleType(object.templateName)
	
	if not player.isCommander():
		if vehicleType == VEHICLE_TYPE_SOLDIER:
			player.score.teamDamages += 1
			addScore(player, SCORE_TEAMDAMAGE, RPL)
		else:
			player.score.teamVehicleDamages += 1
			addScore(player, SCORE_TEAMVEHICLEDAMAGE, RPL)



# prevent point-exploiting by replenishing same player again
def checkGrindBlockRemote(player, object):

	if not hasattr(player, 'lastDestroyedRemote'):
		player.lastDestroyedRemote = {}
	else:	
		if object in player.lastDestroyedRemote:
			if player.lastDestroyedRemote[object] + REPLENISH_POINT_MIN_INTERVAL > host.timer_getWallTime():
				return True

	player.lastDestroyedRemote[object] = host.timer_getWallTime()
	return False


def delay_off(number):
	global g_delay
	g_delay = False


def onVehicleDestroyed(vehicle, attacker):
	global g_delay
	vehicletype = vehicle.templateName
	if vehicletype == "ru_eng_mtlb":
		if not g_delay:
			g_delay = True
			bf2.Timer(delay_off, 1, 1, 0)
			for mine in ["usmin_claymore_projectile","ger_jet_tornadogr4_w_miff_projectile","vnhgr_betty_projectile","tm62m_mine_projectile","rumin_mon50_projectile","chmin_type66_projectile","at_mine_projectile","insgr_hgr_trap_projectile","arty_ied_projectile","bm21_mines","c4_slam_projectile"]:
				out = [i for i in getObjectsOfTemplate(mine) if getVectorDistance((i[0]).getPosition(), vehicle.getPosition()) < 5]
				if len(out) > 0:
					for k in range(len(out)):
						try_destruct_vehicle(out[k][0], out[k][1])

	elif vehicletype == "glu-1_firebomb_fire_dummy":
		bf2object('glu-1_firebomb_fire', vehicle.getPosition(), True)
	elif vehicletype == "drop_proxy":
		bf2object('civ_bik_atv_proxy', vehicle.getPosition(), True)
	elif vehicletype == "civ_bik_atv_proxy":
		bf2object('civ_bik_atv', vehicle.getPosition(), True)
	elif vehicletype == "smoke_object":
		bf2object('smoke_object_art', vehicle.getPosition(), True)
	elif (str(vehicletype).lower())[0:15] == "rallypoint_hand" and vehicle.getPosition() != (0.0,0.0,0.0):
		addScore(attacker, -8, RPL)
		if not attacker.isAIPlayer():
			game.common.sayall(str(attacker.getName()) + " destroyed a rallypoint [-10]")
		return

	if not attacker.isAIPlayer():
		global g_vehicle_bonus
		if vehicletype.lower() in ["suicide_drone_uav"]:
			game.common.sayall(str(attacker.getName()) + " destroyed an enemy drone [+" + str(SCORE_KILL + int(g_vehicle_bonus[vehicletype.lower()])) + "]")
		elif vehicletype.lower() in ["b1_lancer","aix_f117a_flyover","tu95_flyover"]:
			game.common.sayall(str(attacker.getName()) + " destroyed an enemy bomber [+" + str(SCORE_KILL + int(g_vehicle_bonus[vehicletype.lower()])) + "]")
		elif vehicletype.lower() in ["msta-s","tos1","iraqart_2s1_art","iraqart_bm21_art","plz_05_art","usart_m109","ars_d30","artillery_pzh2000_team2","usart_lw155","sa2","sam_sa3"]:
			game.common.sayall(str(attacker.getName()) + " destroyed an enemy artillery [+" + str(SCORE_KILL + int(g_vehicle_bonus[vehicletype.lower()])) + "]")
		if g_vehicle_bonus.get(vehicletype.lower(), 0) > 0:
			addScore(attacker, int(g_vehicle_bonus[vehicletype.lower()]), SKILL)
	
	
		if attacker != None and vehicle.getTeam() != 0 and vehicle.getTeam() != attacker.getTeam() and vehicle.getIsRemoteControlled():
			if not checkGrindBlockRemote(attacker, vehicle):
				addScore(attacker, SCORE_DESTROYREMOTECONTROLLED, RPL)
				bf2.gameLogic.sendGameEvent(attacker, 10, 5) #10 = Replenish, 5 = DestroyStrategic


def rconExec(cmd):
	return host.rcon_invoke(cmd).strip()


def getVectorDistance(pos1, pos2):
	diffVec = [0.0, 0.0, 0.0]
	diffVec[0] = math.fabs(pos1[0] - pos2[0])
	diffVec[1] = math.fabs(pos1[1] - pos2[1])
	diffVec[2] = math.fabs(pos1[2] - pos2[2])
	 
	return math.sqrt(diffVec[0] * diffVec[0] + diffVec[1] * diffVec[1] + diffVec[2] * diffVec[2])


def say_to_player(message, player):
	for ln in message.splitlines():
		host.sgl_sendTextMessage(player.index, 14, 1, ln.rstrip(), 0)

