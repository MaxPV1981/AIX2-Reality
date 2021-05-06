# AIX2 Reality coop
# Original script from AIX team
# Rework by MaxP

# Working version

TAKEOVERTYPE_CAPTURE = 1
TAKEOVERTYPE_NEUTRALIZE = 2

SCORE_CAPTURE = 6
SCORE_NEUTRALIZE = 4
SCORE_CAPTUREASSIST = 1
SCORE_NEUTRALIZEASSIST = 1
SCORE_DEFEND = 4

g_params = {'players':[], 'kits':[], 'init_done':False, 'side':0, 'restarted':False, 'timelimit':0, 'oneplayer':False, 'server_start':0, 'start_time':0, 'mapinit_done':False, "force_win":0, "art_count":0}

TOP = 0
MIDDLE = 1
BOTTOM = 2

import host
import bf2
import math
import types
import string
import game.maplist
import game.common
import sys
import time
from game.bf2object import bf2object
if sys.platform == 'win32':
	import ntpath as path
elif sys.platform == 'unknown':
	import posixpath as path
from random import randint, random
from game.scoringCommon import addScore, RPL, try_destruct_vehicle, getObjectsOfTemplate, say_to_player, rconExec, getVectorDistance
from game.timer import timer, loop
from game.AirdropManager import AirdropManager, spawnArtyAt, rndDevPosition
from bf2 import g_debug
from bf2.stats.constants import getVehicleType, getKitType

ControlPoints = dict()
SpawnPoints = dict()
ArtyLoop = None
REINFORCEMENTS = False
COMMANDER_RESTRICTED = False
LMS_MODE = False
DIGITS = {"1":"one", "2":"two", "3":"three", "4":"four", "5":"five", "6":"six"}
kham_timer = None

def init():
	# events hook
	global g_params
	host.registerGameStatusHandler(onGameStatusChanged)
	if host.sgl_getIsAIGame() == 1:
		host.sh_setEnableCommander(1)
	else:
		host.sh_setEnableCommander(1)

	host.registerHandler('PlayerConnect', onPlayerConnect, 1)		
	host.registerHandler('TimeLimitReached', onTimeLimitReached, 1)	
	host.registerHandler('PlayerChangeTeams', onTeamChange, 1)
	host.registerHandler('PlayerDisconnect', onPlayerDisconnect, 1)
	g_params['server_start'] = host.timer_getWallTime()
	if g_debug: print("gpm_coop.py initialized")


def g_params_clear():
	global SpawnPoints
	global REINFORCEMENTS
	global g_params
	global ControlPoints
	global ArtyLoop
	global kham_timer
	global Airdrop
	global LMS_MODE
	REINFORCEMENTS = False
	COMMANDER_RESTRICTED = False
	ArtyLoop = None
	LMS_MODE = False
	ControlPoints = dict()
	SpawnPoints = dict()
	Airdrop = AirdropManager()
	g_params['init_done'] = False
	g_params['kits'] = []
	g_params['side'] = 0
	g_params['players'] = []
	g_params['restarted'] = False
	g_params['timelimit'] = 0
	g_params['oneplayer'] = False
	g_params['server_start'] = 0
	g_params['start_time'] = 0
	g_params['pregame_init'] = False
	g_params['mapinit_done'] = False
	g_params['force_win'] = 0
	g_params['art_count'] = 0
	if kham_timer:
		kham_timer.abort()
		kham_timer = None

		
def deinit():
	bf2.triggerManager.destroyAllTriggers()
	g_params_clear()
	host.unregisterGameStatusHandler(onGameStatusChanged)
	if g_debug: print("gpm_coop.py uninitialized")


def onPlayerDisconnect(player):
	global g_params
	players = g_params.get('players',[])
	if not player.isAIPlayer():
		if player.index in players:
			players.remove(player.index)
			g_params['players'] = players
			if len(players) <= 1:
				g_params['oneplayer'] = True


def onPlayerConnect(player):
	global g_params
	players = g_params.get('players', [])
	side = g_params.get('side', 3)
	mapinfo = game.maplist.getCurrentMapInfo()
	if not player.isAIPlayer():
		if len(g_params.get('players',[])) == 0 and not g_params.get('mapinit_done', False) and side == 3: #Run mapdata.py only once
			outglobals = {}
			filepath = path.join(bf2.gameLogic.getModDir(), 'levels', mapinfo.name_lower, 'mapdata.py')
			try:
				execfile(filepath, outglobals)
			except:
				print("Can't load map data on connect: " + str(filepath))
			if type(outglobals[mapinfo.gamemode_lower][mapinfo.size]) == tuple:
				side = outglobals[mapinfo.gamemode_lower][mapinfo.size][0]
				g_params['side'] = outglobals[mapinfo.gamemode_lower][mapinfo.size][0]
			else:
				side = outglobals[mapinfo.gamemode_lower][mapinfo.size]
				g_params['side'] = outglobals[mapinfo.gamemode_lower][mapinfo.size]
		player.setTeam(side)
		if not player.index in players:
			players.append(player.index)
			g_params['players'] = players
		if len(players) > 1:
			g_params['oneplayer'] = False
		else:
			#Simplified layout for some maps
			g_params['oneplayer'] = True


def rndPosition(position, rndMin, rndMax, height):
	r = random() * (rndMax - rndMin) + rndMin
	th = random() * 2 * math.pi
	return (round(position[0] + r * math.cos(th),2), round(position[1] + height,2), round(position[2] + r * math.sin(th),2))


def kham_failsafe(*args):
	# Workaround for khamisiyah bridge bug, just move AT soldiers away from it
	AT_soldiers = [x for x in bf2.playerManager.getPlayers() if (x.isAlive() and not x.isManDown() and x.getTeam() == 2 and x.getKit().templateName in ["NATO_AT","NATO_AT_kham","NATO_AT_predator"] and x.getDefaultVehicle() == bf2.objectManager.getRootParent(x.getVehicle()) and (getVectorDistance(x.getDefaultVehicle().getPosition(), (-976.369,42.000,976.430))) < 250)]
#	print("Found soldiers: ", host.timer_getWallTime(), len(AT_soldiers))
#	game.common.sayall("Found soldiers: " + str(len(AT_soldiers)))
	for soldier in AT_soldiers:
		try:
			print("Moving AT soldier: ", soldier.getVehicle())
			soldier.getDefaultVehicle().setPosition(rndPosition((161.351,43.2345,-100.605), 1, 100, 0))
		except:
			print("Can't move soldier: ", soldier.getDefaultVehicle().templateName, Exception)

def player_health_monitor(player):
	max_health, prev_health, last_damage_time, heal_loop, player_revived = getattr(player, 'hp', [200, 200, None, None, False])
	cursed = getattr(player, 'health_monitor', [None, False])[1]
	iddqd_loop = getattr(player, 'iddqd', None)
	if cursed:
		if heal_loop:
			heal_loop.abort()
			heal_loop = None
		return

	if iddqd_loop:
		iddqd_loop.abort()
		iddqd_loop = None
		return

	if player.isAlive() and not player.isManDown():
		body = player.getDefaultVehicle()
		health = body.getDamage()
		current_time = host.timer_getWallTime()
		abort = False
		# Detecting hit. 6 is the threshold where healing procedure begins, you can try to decrease it.
		if max_health - health > 1:
			decrement = (5.4, 0.0)[heal_loop == None]
			if prev_health + decrement - health > 0.1 and prev_health > 15 and health > 0:
#				game.common.sayall("Hit detect, diff is " + str(prev_health - health) + " (" + str(prev_health) + ", " + str(health) + "), loop: " + str(decrement))
				last_damage_time = host.timer_getWallTime()
				abort = True
			elif (player_revived or current_time - last_damage_time > 5) and not heal_loop:
				# Here you can adjust the time period (1.6) and amount of health (5.4)
				heal_loop = loop(1.2, lambda x: x.setDamage(x.getDamage() + 5.4), body)
				player_revived = False
		else:
			abort = True
	else:
		abort = True

	if heal_loop and abort:
		heal_loop.abort()
		heal_loop = None

	setattr(player, 'hp', [max_health, body.getDamage(), last_damage_time, heal_loop, player_revived])


def onTeamChange(player, isHumanSpawned):
	global g_params
	global kham_timer
	global ControlPoints
	side = g_params.get('side', 0)
	players = g_params.get('players', [])
#	warned = ControlPoints['CP_64_tunis_the_prophets_gate'][5]
	mapinfo = game.maplist.getCurrentMapInfo()
#	game.common.sayall(str(getOccupyingCP(player)))
#	game.common.sayall("Replenish: " + str(REPLENISH_POINT_MIN_INTERVAL))
#	game.common.sayall("Host timer: " + str(host.timer_getWallTime()))
#	game.common.sayall("Timelimit: " + str(g_params.get('timelimit', 3600)))
#	cp = ControlPoints['cpname_khamisiyah_coop64_southkhidi'][0]
#	cp.cp_setParam("unableToChangeTeam", 1)
#	cp.cp_setParam('onlyTakeableByTeam', 1)
#	game.common.sayall("Radius: " + str(float(control_point.getTemplateProperty('radius'))))
#	game.common.sayall("Map time limit: " + str(g_params.get('timelimit',0)))
#	game.common.sayall("Start time: " + str(g_params.get('start_time',host.timer_getWallTime())))
	game.common.sayall("Players: " + str(g_params.get('players', [])))
#	game.common.sayall("Force: " + str(g_params.get('force_win', 0)))
#	game.common.sayall("Diff: " + str(host.timer_getWallTime() - g_params.get('start_time',0)))
#	game.common.sayall("Tickets 1: " + str(bf2.gameLogic.getTickets(1)))
#	game.common.sayall("Tickets 2: " + str(bf2.gameLogic.getTickets(2)))
#	game.common.sayall("Def Tickets 1: " + str(bf2.gameLogic.getDefaultTickets(1)))
#	game.common.sayall("Length: " + str(len(players)))
#	game.common.sayall("Size:" + str(mapinfo.size))
#	game.common.sayall("Side: " + str(side))
#	game.common.sayall("Kits: " + str(g_params.get('kits', [])))
#	game.common.sayall("Init: " + str(g_params.get('init_done', False)))
#	game.common.sayall("Pregame init: " + str(g_params['pregame_init']))
#	game.common.sayall("Mapname: " + str(host.sgl_getMapName()))
#	game.common.sayall("Restarted: " + str(g_params.get('restarted', False)))
#	game.common.sayall("Timelimit: " + str(g_params.get('timelimit', 0)))
	game.common.sayall("One player: " + str(g_params.get('oneplayer', False)))
#	game.common.sayall('\xa73\xa7c1001Last man standing mode activated\xa73\xa7c1001')
#	game.common.sayall("Server start: " + str(g_params.get('server_start', 0)))
#	game.common.sayall("Start time: " + str(g_params.get('start_time', 0)))
#	game.common.sayall("Map init: " + str(g_params.get('mapinit_done', False)))
#	game.common.sayall("Force win: " + str(g_params.get('force_win', 0)))
#	message = host.pers_plrRequestStats(player.index, 1, "rank")
#	vehicle = player.getVehicle()
#	rootvehicle = bf2.objectManager.getRootParent(vehicle)
#	rconExec('ObjectTemplate.activeSafe ControlPoint cpname_khamisiyah_coop64_usfob')
#	cp = ControlPoints['cpname_khamisiyah_coop64_usfob'][0]
#	cp.cp_setParam('unableToChangeTeam', 0)
#	cp.cp_setParam('team', 0)
#	ControlPoints['cpname_khamisiyah_coop64_usfob'][3] = 0
#	cp.getTemplateProperty('minNrToTakeControl', 0)
#	rconExec('ObjectTemplate.setControlPointId %s' % cpid)
#	rconExec('ObjectTemplate.setScatterSpawnPositions 1')
#	rconExec('ObjectTemplate.setSpawnPositionOffset 0/1.25/0')
#	vehicletype = vehicle.templateName
#	kit = player.getKit()
#	kittype = kit.templateName
#	game.common.sayall(str(SpawnPoints.items()))
#	game.common.sayall(str(player.isManDown()))
#	game.common.sayall(str(player.isSquadLeader()))
#        host.rcon_invoke('objectTemplate.deleteComponent soldier_supplyobject')
#	game.common.sayall("World size: " + str(message))
#	vehicle.setPosition((0.0, 0.0, 0.0))
#	createSpawner("mbt_t80bv", 1, 1, (-425.511, 20.6062, 680.808), (80, 0, 0))
#	createSpawner("mbt_t80bv_alt", 1, 1, (-438.236, 20.7284, 679.613), (80, 0, 0))
#	createPlayerSpawnPoint(4, (-244.0, 50.0, 615.0), (0.0, 0.0, 0.0), True, 1)
#	createSpawnPoint(2, (-193, 28, 562), (0, 0, 0))
#(cpid, pos, rot, enter=False, team=None, ttl=None)
#	REINFORCEMENTS = True
#	print("Target objects: ", [x.templateName for x in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.GenericProjectile')])
#	if not kham_timer:
#		kham_timer = loop(30, kham_failsafe, None)
#		kham_timer = bf2.Timer(kham_failsafe, 1, 1, 0)
#		kham_timer.setRecurring(10)
#	if not heal_loop:
#	heal(player)
#	heal_loop = loop(0.67, heal, player)
#	game.common.sayall("Root: " + str(rootvehicle.getTeam()))
#	game.common.sayall("Players: " + str(rootvehicle.getOccupyingPlayers()) + ", len: " + str(len(rootvehicle.getOccupyingPlayers())))
#	game.common.sayall("Params: " + str(getattr(player, 'hp', [200, 200, None, None, False])))
#	game.common.sayall("Inside CP: " + str(player.getIsInsideCP()))
#	game.common.sayall("Rank: " + str(player.score.rank))
#	game.common.sayall("Valid: " + str(player.isValid))
#	game.common.sayall("Alive: " + str(player.isAlive()))
#	game.common.sayall("Man Down: " + str(player.isManDown()))
#	host.rcon_invoke("host.sh_setEnableCommander(0)")
#	game.common.sayall("Cheats: " + str(getattr(player, 'cheats', [])))
#	game.common.sayall("CP condition: " + str(ControlPoints['cpname_khamisiyah_coop64_chemfacil'][6]))
#	game.common.sayall("Root vehicle: " + str(bf2.objectManager.getRootParent(vehicle).templateName))
#	game.common.sayall("Vehtype: " + str(getVehicleType(vehicletype)))
#	game.common.sayall("Kittype: " + str(getKitType(kittype)))
#	game.common.sayall("Position: " + str(player.getVehicle().getPosition()))
#	at_list = []
#	for unit in bf2.playerManager.getPlayers():
#		kit = unit.getKit()
#		if unit.getTeam() == 2 and getKitType(kit.templateName) == 0:
#			at_list.append(kit)

#	at_list = [True for x in bf2.playerManager.getPlayers() if (x.getTeam() == 2 and x.getKit().templateName in ["NATO_AT","NATO_AT_kham","NATO_AT_predator","NATO_AT"])]
#	game.common.sayall("List: " + str(at_list))
#	count = len(at_list)
#	squads = host.rcon_invoke('squadManager.listSquads ' + str(side)).split('\n')[:-1]
#	game.common.sayall("AT units count: " + str(count))
#	host.rcon_invoke('squadManager.changeSquadName')
#	createPlayerSpawnPoint(5, (0.0, 51.0, 0.0), (0.0, 0.0, 0.0), True, 1)

	if not player.isAIPlayer():
		if side in [1,2] and player.getTeam() != side:
			message = ("You have to play the " + str(bf2.gameLogic.getTeamName(side)) + " side only!")
			player.setTeam(side)
			address = player.getAddress()
			if not address[0:3] in [127]:
#				string = ("bf2.gameLogic.sendServerMessage(%s, %s)" % (player.index, message))
#				rconExec(str(string))
				say_to_player(message, player)
			else:
				game.common.sayall(message)
		if not player.index in players:
			players.append(player.index)
			g_params['players'] = players


def onGameStatusChanged(status):
	global ControlPoints
	global SpawnPoints
	global g_params
	side = g_params.get('side', 0)
	players = g_params.get('players', [])
	if status == bf2.GameStatus.Playing:
		g_params['start_time'] = host.timer_getWallTime() - g_params.get('server_start', 0)

		# add control point triggers
		for control_point in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.ControlPoint'):
			radius = float(control_point.getTemplateProperty('radius'))
			isHemi = int(control_point.cp_getParam('isHemisphere'))
			if isHemi != 0:
				id = bf2.triggerManager.createHemiSphericalTrigger(control_point, onCPTrigger, '<<PCO>>', radius, (1, 2, 3))
			else:
				id = bf2.triggerManager.createRadiusTrigger(control_point, onCPTrigger, '<<PCO>>', radius, (1, 2, 3))			
			control_point.triggerId = id
			control_point.lastAttackingTeam = 0
			if control_point.cp_getParam('team') > 0:
				control_point.flagPosition = TOP
			else:
				control_point.flagPosition = BOTTOM

			#Forming a control points dictionary
			ControlPoints[control_point.templateName] = [control_point, float(control_point.getTemplateProperty('radius')), int(control_point.cp_getParam('isHemisphere')), 
									control_point.cp_getParam('team'), control_point.getTemplateProperty('ControlPointID'), [], False]
		host.registerHandler('ControlPointChangedOwner', onCPStatusChange)
		host.registerHandler('PlayerDeath', onPlayerDeath)
		host.registerHandler('PlayerKilled', onPlayerKilled)
		host.registerHandler('PlayerRevived', onPlayerRevived)
		host.registerHandler('PlayerSpawn', onPlayerSpawn)
		host.registerHandler('EnterVehicle', onEnterVehicle)
		host.registerHandler('ExitVehicle', onExitVehicle)
		host.registerHandler('PlayerChangeWeapon', onPlayerChangeWeapon)
		host.registerHandler('TicketLimitReached', onTicketLimitReached)
#		host.registerHandler('ConsoleSendCommand', onConsoleSendCommand)
		host.registerHandler('RemoteCommand', onRemoteCommand)
#		host.registerHandler('ClientCommand', onClientCommand)
		host.registerHandler('ChatMessage', onChatMessage)
		host.registerHandler('ChangedCommander', onChangedCommander)
	
		# setup ticket system
		ticketsTeam1 = 0
		ticketsTeam2 = 0
		var1 = 0
		var2 = 0
		if side != 0:
			#Firstly, calculates increased tickets amount if number of bots > 60
			num_allies = int(bf2.playerManager.getNumberOfPlayersInTeam(side))
			num_enemies = int(bf2.playerManager.getNumberOfPlayers() - num_allies)
			var1 = int(bf2.gameLogic.getDefaultTickets(1) * (bf2.serverSettings.getTicketRatio() / 100.0) * max((round(num_enemies / 60.0, 1)), 1))
			var2 = int(bf2.gameLogic.getDefaultTickets(2) * (bf2.serverSettings.getTicketRatio() / 100.0) * max((round(num_enemies / 60.0, 1)), 1))

		#Secondly, calculates increased amount of tickets, depending on players count, and selects maximum from all values
		if side == 2 and bf2.gameLogic.getDefaultTicketLossPerMin(1) > 0 and bf2.serverSettings.getTimeLimit() >= 2400 and not g_params.get('oneplayer', False) and host.sgl_getMapName() != "pointe_du_hoc":
			ticketsTeam1 = max((calcStartTickets(bf2.gameLogic.getDefaultTickets(1)) * max(1, (1 + (len(players) - 1)/4))), var1)
			ticketsTeam2 = calcStartTickets(bf2.gameLogic.getDefaultTickets(2))
		elif side == 1 and bf2.gameLogic.getDefaultTicketLossPerMin(2) > 0 and bf2.serverSettings.getTimeLimit() >= 2400 and not g_params.get('oneplayer', False) and host.sgl_getMapName() != "pointe_du_hoc":
			ticketsTeam1 = calcStartTickets(bf2.gameLogic.getDefaultTickets(1))
			ticketsTeam2 = max((calcStartTickets(bf2.gameLogic.getDefaultTickets(2)) * max(1, (1 + (len(players) - 1)/4))), var2)
		else:
			ticketsTeam1 = calcStartTickets(bf2.gameLogic.getDefaultTickets(1))
			ticketsTeam2 = calcStartTickets(bf2.gameLogic.getDefaultTickets(2))

		bf2.gameLogic.setTickets(1, ticketsTeam1)
		bf2.gameLogic.setTickets(2, ticketsTeam2)

		bf2.gameLogic.setTicketState(1, 0)
		bf2.gameLogic.setTicketState(2, 0)

		bf2.gameLogic.setTicketLimit(1, 1, 0)
		bf2.gameLogic.setTicketLimit(2, 1, 0)
		bf2.gameLogic.setTicketLimit(1, 2, 10)
		bf2.gameLogic.setTicketLimit(2, 2, 10)
		bf2.gameLogic.setTicketLimit(1, 3, int(ticketsTeam1*0.1))
		bf2.gameLogic.setTicketLimit(2, 3, int(ticketsTeam2*0.1))
		bf2.gameLogic.setTicketLimit(1, 4, int(ticketsTeam1*0.2))
		bf2.gameLogic.setTicketLimit(2, 4, int(ticketsTeam1*0.2))

		updateTicketLoss()
	
		if g_debug: print("co-op gamemode initialized.")
	else:
		bf2.triggerManager.destroyAllTriggers()
		if status == bf2.GameStatus.PreGame:
			#before players spawn
			allplayers = bf2.playerManager.getPlayers()
			for candidate in allplayers:
				if not candidate.isAIPlayer() and not candidate.index in players:
					players.append(candidate.index)

			g_params['players'] = players
			if not g_params.get('restarted', False):
				if not g_params.get('pregame_init', False):
					g_params['pregame_init'] = True
					if g_params.get('timelimit', 0) == 0 and bf2.serverSettings.getTimeLimit() < 7000:
						g_params['timelimit'] = bf2.serverSettings.getTimeLimit()
						rconExec("sv.timeLimit 8000")
					if side == 0:
						mapinfo = game.maplist.getCurrentMapInfo()
						outglobals = {}
						filepath = path.join(bf2.gameLogic.getModDir(), 'levels', mapinfo.name_lower, 'mapdata.py')
						try:
							execfile(filepath, outglobals)
						except:
							print("Can't load map data in PreGame: " + str(filepath))
						if type(outglobals[mapinfo.gamemode_lower][mapinfo.size]) == tuple:
							side = outglobals[mapinfo.gamemode_lower][mapinfo.size][0]
							g_params['side'] = side
							g_params['kits'] = outglobals[mapinfo.gamemode_lower][mapinfo.size][1]
						else:
							side = outglobals[mapinfo.gamemode_lower][mapinfo.size]
							g_params['side'] = side
							g_params['kits'] = []
						for index in players:
							player = bf2.playerManager.getPlayerByIndex(index)
							if not player.isAIPlayer():
								if side in [1,2] and not player.getTeam() == side:
									player.setTeam(side)

			for spawn_point in bf2.objectManager.getObjectsOfType('dice.bf.SpawnPoint'):
				SpawnPoints[spawn_point.templateName] = getObjectsOfTemplate(spawn_point.templateName)[0][1]

			#actually this is the real restart (players spawned)
		elif status == bf2.GameStatus.Loaded:
			mapinit()

		elif status == bf2.GameStatus.EndGame:
			g_params_clear()


def onChangedCommander(teamID, oldCommanderPlayerObject, newCommanderPlayerObject):
	if COMMANDER_RESTRICTED:
		origin = newCommanderPlayerObject.getTeam()
		opposite_team = 3 - origin
		#int(abs(origin - 1))
		message = ("You have no commander options on this map")
		say_to_player(message, newCommanderPlayerObject)
		newCommanderPlayerObject.setTeam(opposite_team)
		newCommanderPlayerObject.setTeam(origin)


def unpause(*args):
	rconExec("gamelogic.togglepause")


def onChatMessage(playerId, text, channel, flags):
	global SpawnPoints
	player = bf2.playerManager.getPlayerByIndex(playerId)
	vehicle = player.getDefaultVehicle()
	cheats = getattr(player, 'cheats', [])
	def rndPosition(position, rndMin, rndMax, height):
		r = random() * (rndMax - rndMin) + rndMin
		th = random() * 2 * math.pi
		return (round(position[0] + r * math.cos(th),2), round(position[1] + height,2), round(position[2] + r * math.sin(th),2))

	if player.score.rank >= 4 and not player.isManDown(): # and player.score.rplScore >= 0
		if "give me" in text:
			if "a tank" in text:
				if "please" in text:
					if not "tank" in cheats:
						vehicles = [x.templateName for x in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.PlayerControlObject') if getVehicleType(x.templateName) == 0]
						if len(vehicles) > 0:
							vehicle_instance = vehicles[randint(0, len(vehicles)) - 1]
							obj = bf2object(vehicle_instance, rndPosition(vehicle.getPosition(), 5, 15, 0), True)
							cheats.append("tank")
					else:
						say_to_player("Again?! You eat too much.", player)
				else:
					say_to_player("Something else? Girls, beer?", player)
			if "beer" in text:
				if "tank" in text:
					say_to_player("It is not a good idea to drink and drive.", player)
				elif "girls" in text:
					say_to_player("Are you at war or not? Come back to fight.", player)
				else:
					say_to_player("It is not very good. You better to take the tank.", player)
			if "the tank" in text:
				say_to_player("What tank exactly do you need? Color, condition, mileage?", player)

		if "gravity" in text:
			plist = text.split()
			value = int(plist[1])
			rconExec("physics.gravity %s" % value)

		if "where am I" in text:
			pos = ', '.join(map(lambda x: str(int(x)), vehicle.getPosition()))
			message = ("You are at (" + str(pos) + ")")
			say_to_player(message, player)

		if "to an empty vehicle" in text:
			vehicles = [[getVectorDistance(x.getPosition(), vehicle.getPosition()), x.getPosition()] for x in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.PlayerControlObject') if x.getPosition() != (0.0, 0.0, 0.0) and getVehicleType(x.templateName) in [0,1,3,4] and len(x.getOccupyingPlayers()) == 0 and x.getTeam() in [0,1]]
			if len(vehicles) > 0:
				vehicles.sort()
				rootVehicle = bf2.objectManager.getRootParent(vehicle)
				rootVehicle.setPosition(rndPosition(vehicles[0][1], 2, 5, 0))
			else:
				say_to_player("There are no empty vehicles on a map", player)

		if "to my leader" in text or "to my squad leader" in text or "to my squadleader" in text:
			if player.isSquadLeader():
				say_to_player("Are you normal? You are the squad leader.", player)
				return

			for candidate in bf2.playerManager.getPlayers():
				if candidate != player:
					if candidate.getTeam() == player.getTeam() and candidate.getSquadId() == player.getSquadId() and candidate.isSquadLeader():
						if candidate.isAlive():
							vehicle.setPosition(rndPosition(candidate.getVehicle().getPosition(), 2, 10, 0))
							break
						else:
							say_to_player("Your squad leader is dead", player)

		if "teleport me" in text and not "leader" in text:
			rootVehicle = bf2.objectManager.getRootParent(vehicle)
			if "somewhere" in text:
				worldsize = host.sgl_getWorldSize()[0] / 3
				rootVehicle.setPosition(rndPosition((0,rootVehicle.getPosition()[1],0), 1, worldsize, 0))
			elif "teleport me to" in text and (not "teleport" in cheats or "MaxPV" in player.getName()):
				if "(" in text and ")" in text:
					coords = text[text.index("(") + 1: text.index(")")]
					splitted = tuple(map(float, coords.split(',')))
					rootVehicle.setPosition(splitted)
					cheats.append("teleport")
				else:
					plist = text.split()
					index = plist.index("to") + 1
					name = plist[index]
					if len(plist) == 5:
						name = ' '.join([name, plist[index + 1]])
					for candidate in bf2.playerManager.getPlayers():
						if name in candidate.getName():
							vehicle.setPosition(rndPosition(candidate.getVehicle().getPosition(), 5, 10, 0))
							vehicle.setRotation(candidate.getVehicle().getRotation())
							cheats.append("teleport")
							break

		if "rcon exec" in text:
			index = text.index("rcon exec")
			command = text[index + len("rcon exec"):len(text)]
			print("Rcon command: ", command)
			rconExec(command)

		if "pause for" in text and not "pause" in cheats:
			number = ""
			seconds = not "minut" in text
			print("Seconds: ", seconds)
			for char in text:
				if char.isdigit():
					number += char
			number = int(number)
			print("Number: ", number)
			max_nr = (15,900)[seconds]
			if number > 0 and number < max_nr:
				print("Timer passed: ", (int(number*60), number)[seconds])
#				timer.once(1, unpause, None)
				timer.once((int(number*60), number)[seconds], unpause, None)
				rconExec("gamelogic.togglepause")
			else:
				say_to_player("Enter a value between 1 and 15 minutes or between 1 and 900 seconds", player)

		if "burn me" in text and not "burn" in cheats:
			obj = bf2object('glu-1_firebomb_fire', vehicle.getPosition(), True)
			cheats.append("burn")

		if "heal me" in text:
			vehicle.setDamage(200)

		if "iddqd" in text and not "iddqd" in cheats:
			vehicle.setDamage(2000)
			iddqd_loop = loop(0.66, lambda x: x.setDamage(x.getDamage() + 150), vehicle)
			setattr(player, 'iddqd', iddqd_loop)
			cheats.append("iddqd")

		if "restart" in text and not "restart" in cheats:
			rconExec("admin.restartmap")
			mapinit()
			cheats.append("restart")

		if "last man standing" in text and not "last" in cheats:
			for sp_id in SpawnPoints.values():
				rconExec('object.active id%d' % int(sp_id))
				rconExec('object.delete')
			SpawnPoints.clear()

			rconExec("aisettings.setrespawnallowed 0")
			for spawner in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.ObjectSpawner'):
				print(spawner)
				deleteSpawner(spawner)

			for bot in bf2.playerManager.getPlayers():
				if bot.isAlive():
					body = bot.getDefaultVehicle()
					rootVehicle = bf2.objectManager.getRootParent(body)
					if body != rootVehicle:
						rootVehicle.setDamage(0.1)

			for vehicle in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.PlayerControlObject'):
				vehicle.setDamage(0.1)

			cheats.append("last")

		if "destroy all mines" in text and not "mines" in cheats:
			for mine in ["usmin_claymore_projectile","ger_jet_tornadogr4_w_miff_projectile","vnhgr_betty_projectile","tm62m_mine_projectile","rumin_mon50_projectile","chmin_type66_projectile","at_mine_projectile","insgr_hgr_trap_projectile","arty_ied_projectile","bm21_mines","c4_slam_projectile"]:
				out = [i for i in getObjectsOfTemplate(mine)]
				if len(out) > 0:
					for k in range(len(out)):
						try_destruct_vehicle(out[k][0], out[k][1])
			cheats.append("mines")

		if "karma" in text:
			killer_dict = getattr(player, 'killer_dict', None)
			if killer_dict:
				overall = killer_dict.get('overall', 0)
				message = ""
				for victim in killer_dict.keys():
					if victim != 'overall':
						value = killer_dict.get(victim, 0)
						message = message + (", ", "")[message == ""] + str(value) + " to " + str(victim)

				say_to_player(message, player)
				say_to_player("Overall " + str(overall), player)
			else:
				say_to_player("You're clean before the Emperor", player)

		if "tickets" in text and not "tickets" in cheats:
			sign = (1,-1)["take" in text]
			number = ""
			for char in text:
				if char == "-" and number == "":
					number = "-"
				if char.isdigit():
					number += char
			number = int(number)
			say_to_player(("Number: " + str(sign) + str(number)), player)
			team = player.getTeam()
			enemy_team = 3 - team

			if "give" in text and "from" in text or "take" in text and " to " in text:
				say_to_player("Are you drunk?", player)

			if "enemy" in text:
				teamTickets = bf2.gameLogic.getTickets(enemy_team)
				teamTickets = teamTickets + (number * sign)
				bf2.gameLogic.setTickets(enemy_team, teamTickets)
				cheats.append("tickets")
			else:
				teamTickets = bf2.gameLogic.getTickets(team)
				teamTickets = teamTickets + (number * sign)
				bf2.gameLogic.setTickets(team, teamTickets)
				cheats.append("tickets")

		if "repair me" in text and not "repair" in cheats:
			rootVehicle = bf2.objectManager.getRootParent(vehicle)
			current_vehicle = player.getVehicle()
#			say_to_player("Vehicle: " + str(current_vehicle.templateName), player)
			current_vehicle.setDamage(2500)
			rootVehicle.setDamage(2500)
			cheats.append("repair")

		if "kill'em all" in text and not "kill" in cheats:
			human_team = player.getTeam()
			for cp in ControlPoints:
				if ControlPoints[cp][3] != human_team:
					ControlPoints[cp][3] = human_team
					ControlPoints[cp][0].cp_setParam('team', human_team)
	
			for bot in bf2.playerManager.getPlayers():
				if bot.isAlive() and bot.getTeam() != human_team:
					body = bot.getDefaultVehicle()
					rootVehicle = bf2.objectManager.getRootParent(body)
					if body == rootVehicle:
						body.setDamage(0)
					else:
						rootVehicle.setDamage(1)
						for crew_member in rootVehicle.getOccupyingPlayers():
							timer.once(3, delayed_bot_kill, crew_member)
			cheats.append("kill")

		if "bring my squad here" in text:
			squad = player.getSquadId()
			for candidate in bf2.playerManager.getPlayers():
				if candidate.isAlive() and candidate.getSquadId() == squad and candidate.getTeam() == player.getTeam() and candidate != player and candidate.getDefaultVehicle() == candidate.getVehicle():
					body = candidate.getDefaultVehicle()
					body.setPosition(rndPosition(vehicle.getPosition(), 2, 10, 0))
					messages = ["I'm with you","Here!","Here I am","With you","Yup","That teleport thing make me sick","Don't do it again, ok?","What's up?","Where am I?!","What we gonna do here?"]
					message = "<SQUAD>" + candidate.getName() + ": " + messages[randint(0,len(messages) - 1)]
					say_to_player(message, player)
#			cheats.append("squad")

		if "bring my team here" in text and not "team" in cheats:
			for candidate in bf2.playerManager.getPlayers():
				if candidate.isAlive() and candidate.getTeam() == player.getTeam() and candidate != player and candidate.getDefaultVehicle() == candidate.getVehicle():
					body = candidate.getDefaultVehicle()
					body.setPosition(rndPosition(vehicle.getPosition(), 2, 10, 0))
					messages = ["I'm with you","Here!","Here I am","With you","Yup","That teleport thing make me sick","Don't do it again, ok?","What's up?","Where am I?!","What we gonna do here?","The whole team?!","What will our commander say?"]
					message = "<TEAM>" + candidate.getName() + ": " + messages[randint(0,len(messages) - 1)]
					say_to_player(message, player)
			cheats.append("team")

		setattr(player, 'cheats', cheats)


def delayed_bot_kill(crew_member):
	body = crew_member.getDefaultVehicle()
	vehicle = crew_member.getVehicle()
	rootVehicle = bf2.objectManager.getRootParent(body)
	if crew_member.isAlive() and body == rootVehicle:
		try:
			body.setDamage(0)
		except:
			print("Can't kill: ", body.templateName, vehicle.templateName, rootVehicle.templateName)


def timerEventHandler(*args):
	for point, team in args:
		point.cp_setParam('team', team)


#def onConsoleSendCommand(command, args):
#	game.common.sayall("Console send command: " + str(command))


def onRemoteCommand(playerId, subcmd):
	global g_params
#	game.common.sayall("Remote command: " + str(subcmd))
	player = bf2.playerManager.getPlayerByIndex(playerId)
	soldier = player.getDefaultVehicle()
	pos = soldier.getPosition()
	if soldier:
		if subcmd == "supplydrop":
			Airdrop.startSupplydrop(player.getTeam(), pos, player)
		elif subcmd == "vehicledrop":
			Airdrop.startVehicledrop(player.getTeam(), pos, player)
		elif subcmd == "artillery":
#			artyObj = bf2object("art_decoy", pos, True)
			projectiles = [x for x in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.GenericProjectile') if x.templateName == 'LaserTarget_Projectile']
			if projectiles:
				pos = projectiles[0].getPosition()
				Airdrop.startArtillery(player.getTeam(), pos, player)
			else:
				say_to_player("No target coordinates, use you simrad to point your artillery", player)

		elif subcmd == "retreat":
			for candidate in bf2.playerManager.getPlayers():
				if not candidate.isAIPlayer() and candidate.getTeam() == player.getTeam() and candidate.getSquadId() == player.getSquadId():
					variant = ["Retreat!", "Fall back!"][randint(0, 1)]
					message = (str(player.getName()) + ": " + str(variant))
					say_to_player(message, candidate)
			

#def onClientCommand(command, issuerPlayerObject, args):
#	game.common.sayall("Client command: " + str(command)) 


def mapinit(players=[]):
	global ControlPoints
	global g_params
	global COMMANDER_RESTRICTED
	global LMS_MODE
	if g_params.get('mapinit_done', False):
		return
	g_params['mapinit_done'] = True
	mapinfo = game.maplist.getCurrentMapInfo()
	print(str(host.sgl_getMapName()) + " loading at " + str(host.timer_getWallTime()))
	if len(g_params.get('players', [])) > 1:
		oneplayer = False
		g_params['oneplayer'] = False
	else:
		oneplayer = True
		g_params['oneplayer'] = True

	side = g_params.get('side', 0)
	kits = g_params.get('kits', [])

	# This is the workaround for invisible kits, which should be spawned on captured points during the game.
	# Its geometry needs to be initialized at start, or kits wouldn't be showed
	if len(kits) > 0:
		for key in ControlPoints:
			if ControlPoints[key][3] and ControlPoints[key][3] in [1,2]:
				tside = ControlPoints[key][3]
				for kit in kits:
					createKit(kit, ControlPoints[key][4], int(tside), ((int(kits.index(kit))), 1000, 0))
#					print(str(kit) + " created")
				break

	if host.sgl_getMapName() == "pointe_du_hoc":
		COMMANDER_RESTRICTED = True
		if mapinfo.size == 64:
			for cp_name in ["64_CP_farm1","64_CP_farm2","CP_64_reinforcements_1","CP_64_reinforcements_2","64_CP_bunkers3"]:
				teamvalue = ControlPoints[cp_name][3]
				cp = ControlPoints[cp_name][0]
				cp.cp_setParam('team', 0)
				bf2.Timer(timerEventHandler, 1, 1, (cp, teamvalue))
		elif mapinfo.size == 32:
			LMS_MODE = True
			bf2.gameLogic.setTickets(1, 9999)
			g_params['force_win'] = side
			# It means the map can be won by holding at least one point till the end of time limit

	elif host.sgl_getMapName() == "Heaven_And_Hell_Revisited":
		LMS_MODE = True
		COMMANDER_RESTRICTED = True
		for cp_name in ["Transmission_Towers","Maingate","Barracks","Underground_Entrance"]:
			teamvalue = ControlPoints[cp_name][3]
			cp = ControlPoints[cp_name][0]
			cp.cp_setParam('team', 0)
			bf2.Timer(timerEventHandler, 1, 1, (cp, teamvalue))

	elif host.sgl_getMapName() == "dovre_winter" and mapinfo.size == 64:
		COMMANDER_RESTRICTED = True
		for cp_name in ["cpname_dovre_winter_coop64_farm","cpname_dovre_winter_coop64_station_houses","cpname_dovre_winter_coop64_station","cpname_dovre_winter_coop64_station_second","cpname_dovre_winter_coop64_station_houses"]:
			teamvalue = ControlPoints[cp_name][3]
			cp = ControlPoints[cp_name][0]
			cp.cp_setParam('team', 0)
			bf2.Timer(timerEventHandler, 1, 1, (cp, teamvalue))

	elif host.sgl_getMapName() == "sidi_bou_zid":
		if mapinfo.size == 64:
			if oneplayer:
				createSpawner("ru_jet_su25a_sp", 101, 1, (695.094, 42.815, -714.961), (25.5, 0, 0), 1200)
		else:
			COMMANDER_RESTRICTED = True

	elif host.sgl_getMapName() == "mareth_line":
		COMMANDER_RESTRICTED = True
		if mapinfo.size == 64:
			if oneplayer:
				for vehicle, vehicle_id in getObjectsOfTemplate("deployable_spg9_sp"):
					if vehicle.getPosition() != (0.0,0.0,0.0):
						try_destruct_vehicle(vehicle, vehicle_id)
	
				deleteSpawner("CP_64_mareth_Medenine_heli_5")
				deleteSpawner("CP_64_mareth_Command_Bunker_HeavyAT")
				deleteSpawner("CP_64_mareth_Mareth_AntiAirSmall")
				deleteSpawner("CP_64_mareth_Toujane_spg9")
				deleteSpawner("CP_64_mareth_Mareth_pak38")
				deleteSpawner("CP_64_mareth_Mareth_spg9_1")
				deleteSpawner("CP_64_mareth_Mareth_cannon")
				deleteSpawner("CP_64_mareth_Command_Bunker_kwk5cm")
				createSpawner("mec_ats_milan", 5, 1, (-515.376, 35.8947, 307.851), (-170, 0, 0))
				createSpawner("mec_ats_milan", 3, 1, (-262.106, 24.7202, 209.575), (-190, 0, 0))
				createSpawner("mec_ats_milan", 7, 1, (-403.857, 24.4036, -14.9918), (100, 0, 0))
				createSpawner("mec_ats_milan", 3, 1, (-117.335, 25.0, 220.030), (-160, 0, 0))
				createSpawner("mec_ats_milan", 3, 1, (-176.531, 24.8405, 237.143), (-180, 0, 0))
				createSpawner("mec_ats_milan", 3, 1, (-346.874, 32.6104, 119.037), (109, 0, 0))
				createSpawner("mec_ats_milan", 5, 1, (-399.508, 60.54, 208.339), (130, 0, 0))
				game.common.sayall("Simplified layout loaded")

			vehicles_set = [
				[("us_tnk_m1a2_alt","us_tnk_m1a2","fr_tnk_leclerc","gb_tnk_challenger_alt","leopard_2a7","us_tnk_m1a2_alt","us_tnk_m1a2"),2,2,(8.35962,25.3712,-501.443),(0,0,0),180,False,2],
				[("us_aav_avenger_bf2","usaav_m6","ger_aav_fennekswp"),2,2,(-36.959,26.657,-489.083),(0,0,0),240,False,2],
				[("us_ifv_m2a2","us_apc_lav25","gb_apc_warrior","gb_ifv_scimitar_cage","cf_apc_lav3","us_apc_stryker_mk19","fr_apc_vbci_bf2_alt"),2,2,(-45.602,26.670,-471.892),(90,0,0),180,False,2],
				[("us_ifv_m2a2","us_apc_lav25","gb_apc_warrior","gb_ifv_scimitar_cage","cf_apc_lav3","us_apc_stryker_mk19","fr_apc_vbci_bf2_alt"),2,2,(-60.510,24.862,-463.779),(0,0,0),180,False,2],
				[("us_tnk_m1a2_alt","us_tnk_m1a2","fr_tnk_leclerc","gb_tnk_challenger_alt","leopard_2a7","us_tnk_m1a2_alt","us_tnk_m1a2"),2,2,(-75.343,24.877,-464.2),(270,0,0),180,False,2],
				[("us_tnk_m1a2_alt","us_tnk_m1a2","fr_tnk_leclerc","gb_tnk_challenger_alt","leopard_2a7","us_tnk_m1a2_alt","us_tnk_m1a2"),2,2,(-125.636,27.7189,-467.132),(270,0,0),180,False,2],
				[("us_ifv_m2a2","us_apc_lav25","gb_apc_warrior","gb_ifv_scimitar_cage","cf_apc_lav3","us_apc_stryker_mk19","fr_apc_vbci_bf2_alt"),2,2,(-91.040,24.590,-423.262),(180,0,0),180,False,2],
				[("us_tnk_m1a2_alt","us_tnk_m1a2","fr_tnk_leclerc","gb_tnk_challenger_alt","leopard_2a7","us_tnk_m1a2_alt","us_tnk_m1a2"),2,2,(-77.969,24.920,-422.645),(90,0,0),180,False,2],
				[("us_ahe_apache","rah66a"),2,2,(-76.3677,26.8149,-872.581),(90,0,0),420,True,None]
			]

			for vehicles, cp, team, coords, rot, spawn_delay, delayed, maxnr_to_spawn in vehicles_set:
				print("Calling spawner: ",vehicles, cp, team, coords, rot, spawn_delay, delayed, maxnr_to_spawn)
				createSpawner(vehicles[randint(0, len(vehicles) - 1)], cp, team, coords, rot, spawn_delay, delayed, maxnr_to_spawn)

			createSpawner("hoverbug", 4, 1, (292.454,27.9207,-609.024), (0,0,0), 9999, False)

			teamvalue = ControlPoints["CP_64_mareth_Medenine"][3]
			cp = ControlPoints["CP_64_mareth_Medenine"][0]
			cp.cp_setParam('team', 0)
			bf2.Timer(timerEventHandler, 40, 1, (cp, teamvalue))

		elif mapinfo.size == 16:
			bf2.gameLogic.setTickets(2, 9999)
			g_params['force_win'] = side
		elif mapinfo.size == 32:
			pass

	elif host.sgl_getMapName() == "st_lo_breakthrough":
		LMS_MODE = True
		COMMANDER_RESTRICTED = True
		bf2.gameLogic.setTickets(2, 9999)
		g_params['force_win'] = side

	elif host.sgl_getMapName() == "OmahaBeach2011" and mapinfo.size == 64:
		LMS_MODE = True
		COMMANDER_RESTRICTED = True
		if oneplayer:
			for vehicle, vehicle_id in getObjectsOfTemplate("ddg83_sp"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)
			deleteSpawner("CP_DDG83")
			game.common.sayall("Simplified layout loaded")
		g_params['force_win'] = side

	elif host.sgl_getMapName() == "MountainsConvoysAirAttack":
		COMMANDER_RESTRICTED = True
		for vehicle, vehicle_id in getObjectsOfTemplate("tomahawk_missile"):
			try_destruct_vehicle(vehicle, vehicle_id)

	elif host.sgl_getMapName() == "kashan_desert" and mapinfo.size == 32:
		game.common.sayall("Await for a massive attack after several minutes")

	elif host.sgl_getMapName() == "khamisiyah" and mapinfo.size == 64:
		teamvalue = ControlPoints["cpname_khamisiyah_coop64_chemfacil"][3]
		cp = ControlPoints["cpname_khamisiyah_coop64_chemfacil"][0]
		cp.cp_setParam('team', 0)
		deleteSpawner("cpname_khamisiyah_coop64_b1_prespawn")
		if oneplayer:
			bf2.Timer(timerEventHandler, 60, 1, (cp, teamvalue))
			deleteSpawner("cpname_khamisiyah_coop64_chemical_art")
			deleteSpawner("cpname_khamisiyah_coop64_village_hmmwv")
			deleteSpawner("cpname_khamisiyah_coop128_bunkers_heli")
			deleteSpawner("cpname_khamisiyah_coop64_mecmain_hind")

			for vehicle, vehicle_id in getObjectsOfTemplate("usart_m270"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)

			game.common.sayall("Simplified layout loaded")
		else:
			deleteSpawner("cpname_khamisiyah_coop64_djigit")
			deleteSpawner("cpname_khamisiyah_coop64_djigit2")
			deleteSpawner("cpname_khamisiyah_coop64_dshk")
			for vehicle, vehicle_id in getObjectsOfTemplate("deployable_mistral_sp"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)
			bf2.Timer(timerEventHandler, 1, 1, (cp, teamvalue))
		nato_planes_set = [
			"AIX_F117A",
			"us_jet_f15",
			"us_jet_a10a_sp",
			"ger_jet_eurofighter_sp",
			"us_jet_f35a",
			"ger_jet_tornadogr4_mw1",
			"us_jet_harrier",
			"ger_jet_eurofighter_sp",
			"us_jet_harrier",
			"cf_jet_cf18_sp",
			"cf_jet_cf18_sp"
		]
		ai_planes_set = [
			"us_jet_harrier",
			"AIX_F117A",
			"us_jet_a10a_tobruk",
			"ger_jet_eurofighter_sp",
			"us_jet_f35a",
			"ger_jet_tornadogr4_mw1",
			"us_jet_harrier",
			"cf_jet_cf18_sp",
			"cf_jet_cf18_sp"
		]
		plane_spawners = [(29.861, 40.701, -1865.44),(73.6765, 40.701, -1865.44),(118.405, 40.701, -1867.45),(161.487, 40.701, -1865.44)]
		ai_spawners = [[(271.056, 40.701, -2028.613),(92,0,0)],[(271.333, 40.701, -2002.344),(92,0,0)],[(133.41, 40.701, -2012.97),(-90,0,0)]]
		for i in range(4):
			plane = nato_planes_set.pop(randint(0, len(nato_planes_set) - 1))
			createSpawner(plane, 2, 0, plane_spawners[i], (180, 0, 0), randint(1100,1500), True)
		for j in range(3):
			ai_plane = ai_planes_set.pop(randint(0, len(ai_planes_set) - 1))
			createSpawner(ai_plane, 2, 2, ai_spawners[j][0], ai_spawners[j][1], randint(600,700), [False,True][j == 2])
		tanks_set = [
			"cf_tnk_leo2a6",
			"gb_tnk_challenger_alt",
			"fr_tnk_leclerc",
			"us_tnk_m1a2",
			"us_tnk_m1a2_alt",
			"leopard_2a7",
			"us_tnk_m1a2",
			"us_tnk_m1a2_alt"
		]
		apc_set = [
			"us_ifv_m2a2",
			"fr_apc_vbci_bf2_alt",
			"us_apc_lav25",
			"ger_ifv_puma",
			"gb_apc_warrior",
			"gb_ifv_scimitar_cage",
			"cf_apc_lav3"
		]
		aa_set = [
			"ger_aav_fennekswp",
			"gb_aav_stormer",
			"us_aav_avenger_bf2"
		]
		tank_spawners = [
			[(1556.097,38.004,74.468),(-110,0,0)],
			[(1571.672,38.004,80.493),(-110,0,0)],
			[(1586.529,38.004,86.158),(-110,0,0)],
			[(1601.260,38.004,91.791),(-110,0,0)],
			[(1617.390,38.004,97.655),(-110,0,0)],
			[(1633.642,38.004,103.679),(-110,0,0)]
		]
		apc_spawners = [
			[(1575.994,38.004,51.941),(-20,0,0)],
			[(1583.258,38.004,54.268),(-20,0,0)],
			[(1586.276,38.004,71.544),(-110,0,0)],
			[(1595.962,38.004,67.380),(-110,0,0)]
		]
		aa_spawners = [[(1566.843,38.004,48.636),(-20,0,0)]]
		for i in range(len(tank_spawners)):
			vehicle = tanks_set[randint(0, len(tanks_set) - 1)]
			createSpawner(vehicle, 2, 2, tank_spawners[i][0], tank_spawners[i][1], randint(180,320), False, 2)

		for i in range(len(apc_spawners)):
			vehicle = apc_set.pop(randint(0, len(apc_set) - 1))
			createSpawner(vehicle, 2, 2, apc_spawners[i][0], apc_spawners[i][1], randint(120,180), False, 2)

		for i in range(len(aa_spawners)):
			vehicle = aa_set.pop(randint(0, len(aa_set) - 1))
			createSpawner(vehicle, 2, 2, aa_spawners[i][0], aa_spawners[i][1], randint(180,240), False, 2)

	elif host.sgl_getMapName() == "omaha_beach" and mapinfo.size == 64:
		for cp_name in ["CP_64_omaha_vierville","CP_64_omaha_viervilleeast","CP_64_omaha_church"]:
			teamvalue = ControlPoints[cp_name][3]
			cp = ControlPoints[cp_name][0]
			cp.cp_setParam('team', 0)
			bf2.Timer(timerEventHandler, 1, 1, (cp, teamvalue))
		if oneplayer:
			deleteSpawner("CP_64_omaha_puma")
			deleteSpawner("CP_64_omaha_tank")
			for vehicle, vehicle_id in getObjectsOfTemplate("ger_tnk_leo2a6"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)
			for vehicle, vehicle_id in getObjectsOfTemplate("ger_ifv_puma"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)
			game.common.sayall("Simplified layout loaded")

	elif host.sgl_getMapName() == "alam_halfa":
		for cp_name in ["CP_64_AlamHalfa_23d_Armd_Brigade","CP_64_AlamHalfa_22d_Armd_Brigade","CP_64_AlamHalfa_8th_Armd_Brigade"]:
			teamvalue = ControlPoints[cp_name][3]
			cp = ControlPoints[cp_name][0]
			cp.cp_setParam('team', 0)
			bf2.Timer(timerEventHandler, 1, 1, (cp, teamvalue))

	elif host.sgl_getMapName() == "kubra_dam":
		if oneplayer:
			deleteSpawner("CPNAME_KD_64_intake_LJ")
			for cp_name in ["CPNAME_KD_64_refuellingstation","CPNAME_KD_64_supervisorbase","CPNAME_KD_64_materialstation"]:
				cp = ControlPoints[cp_name][0]
				cp.cp_setParam('team', 0)
			cp = ControlPoints["CPNAME_KD_64_bridgebase"][0]
			cp.cp_setParam('team', 1)
			ControlPoints["CPNAME_KD_64_bridgebase"][3] = 1
			game.common.sayall("Simplified layout loaded")
			updateTicketLoss()

	elif host.sgl_getMapName() == "Dragon_Valley" and mapinfo.size == 32 and oneplayer:
		for cp_name in ["CPNAME_DV_32_refinery","CPNAME_DV_32_powerstation","CPNAME_DV_32_hillvillage","CPNAME_DV_32_woodyard","CPNAME_DV_32_islandfarmhouse","CPNAME_DV_32_marketplace","CPNAME_DV_32_rivervillage","CPNAME_DV_32_temple"]:
			cp = ControlPoints[cp_name][0]
			cp.cp_setParam('team', 1)
			ControlPoints[cp_name][3] = 1
		cp = ControlPoints["CPNAME_DV_32_vistapoint"][0]
		cp.cp_setParam('team', 0)
		ControlPoints["CPNAME_DV_32_vistapoint"][3] = 0
		game.common.sayall("Simplified layout loaded")
		updateTicketLoss()

	elif host.sgl_getMapName() == "fushe_pass" and mapinfo.size == 64 and oneplayer:
		for cp_name in ["CPNAME_GP_64_powerplant","CPNAME_GP_64_emineentrance","CPNAME_GP_64_securityhq","CPNAME_GP_64_mountainlookout","CPNAME_GP_64_canyonguardpost","CPNAME_GP_64_wmineentrance","CPNAME_GP_64_bridgecamp","CPNAME_GP_64_uppercamp"]:
			cp = ControlPoints[cp_name][0]
			cp.cp_setParam('team', 0)
		game.common.sayall("Simplified layout loaded")
		updateTicketLoss()

	elif host.sgl_getMapName() == "warlord":
		LMS_MODE = True
		if mapinfo.size == 32:
			if oneplayer:
				for vehicle, vehicle_id in getObjectsOfTemplate("rutnk_t90a"):
					if vehicle.getPosition() != (0.0,0.0,0.0):
						try_destruct_vehicle(vehicle, vehicle_id)
				deleteSpawner("CP_32p_WL_ConstructionSite_0")
				game.common.sayall("Simplified layout loaded")
		elif mapinfo.size == 64:
			bf2.gameLogic.setTickets(2, 9999)
			createKit("Support_GB_Minimi", 1, 1, (75.9249, 110.404, 213.892))
			createKit("Support_US_M240_iron", 1, 1, (77.9978, 110.404, 214.184))
		elif mapinfo.size == 16:
			COMMANDER_RESTRICTED = True
			if oneplayer:
				for vehicle, vehicle_id in getObjectsOfTemplate("rutnk_t90a"):
					if vehicle.getPosition() != (0.0,0.0,0.0):
						try_destruct_vehicle(vehicle, vehicle_id)
				deleteSpawner("CP_16p_WL_ConstructionSite_0")
				game.common.sayall("Simplified layout loaded")
			createKit("ACS_GB", 1, 1, (75.9249, 110.404, 213.892))
			createKit("Support_GB_GPMG_optic", 1, 1, (77.9978, 110.404, 214.184))
			bf2.gameLogic.setTickets(2, 9999)
			g_params['force_win'] = side

	elif host.sgl_getMapName() == "the_battle_for_sfakia":
		LMS_MODE = True
		COMMANDER_RESTRICTED = True
		if mapinfo.size == 64:
			bf2.gameLogic.setTickets(1, 9999)

	elif host.sgl_getMapName() == "new_city":
		COMMANDER_RESTRICTED = True
		if oneplayer:
			for vehicle, vehicle_id in getObjectsOfTemplate("us_ahe_apache_sp"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)
			deleteSpawner("hilltop_tower__Attackheli")
			game.common.sayall("Simplified layout loaded")

	elif host.sgl_getMapName() == "gazala":
		COMMANDER_RESTRICTED = True
		if oneplayer:
			for vehicle, vehicle_id in getObjectsOfTemplate("us_ahe_apache"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)

			for vehicle, vehicle_id in getObjectsOfTemplate("us_jet_a4_bomb"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)

			for vehicle, vehicle_id in getObjectsOfTemplate("ats_tow_nobot"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)

			createSpawner("ats_tow", 304, 1, (-46.190, 50.76, 109.091), (175.419, 0, 0))
			createSpawner("ats_tow", 304, 1, (-61.120, 48.956, 119.249), (-30, 0, 0))
			createSpawner("ats_tow", 304, 1, (-90.084, 48.98, 86.496), (-129, 0, 0))

			deleteSpawner("CP_64_Gazala_TrighCapuzzo_DE_GB_LightbomberPlane_0")
			deleteSpawner("CP_64_Gazala_TrighCapuzzo_DE_GB_FighterPlane")
			game.common.sayall("Simplified layout loaded")

	elif host.sgl_getMapName() == "al_sbeneh_region":
		COMMANDER_RESTRICTED = True
		LMS_MODE = True
		if oneplayer:
			for vehicle, vehicle_id in getObjectsOfTemplate("mec_aav_shilka_bf2"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)

			deleteSpawner("cpname_al_sbeneh_region_fsa_shil")
			deleteSpawner("cpname_al_sbeneh_region_fsa_aa")
			game.common.sayall("Simplified layout loaded")
		bf2.gameLogic.setTickets(2, 9999)
		g_params['force_win'] = side

	elif host.sgl_getMapName() == "muttrah_city_2":
		if oneplayer:
			for vehicle, vehicle_id in getObjectsOfTemplate("us_ahe_ah6"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)

			deleteSpawner("cpname_muttrah_city_2_coop16_carrier_cas")
			deleteSpawner("cpname_muttrah_city_2_coop16_carrier_cas_sp")
			game.common.sayall("Simplified layout loaded")
		bf2.gameLogic.setTickets(2, 9999)
		g_params['force_win'] = side

	elif host.sgl_getMapName() == "highway_tampa":
		if oneplayer:
			for vehicle, vehicle_id in getObjectsOfTemplate("usaav_m6"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)
			deleteSpawner("CPNAME_HT_64_ShahrUrmia_HeavyJeep")
			deleteSpawner("CPNAME_HT_64_ShahrUrmia_FighterBomber_US")
			game.common.sayall("Simplified layout loaded")


	elif host.sgl_getMapName() == "aix_wake_island_2007":
		COMMANDER_RESTRICTED = True
		for cp_name in ["64_CH_CP_NorthVillage","64_CH_CP_Beach"]:
			teamvalue = ControlPoints[cp_name][3]
			cp = ControlPoints[cp_name][0]
			cp.cp_setParam('team', 0)
			bf2.Timer(timerEventHandler, 1, 1, (cp, teamvalue))
		if oneplayer:
			for vehicle, vehicle_id in getObjectsOfTemplate("us_ahe_uh1nrockets"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)
			deleteSpawner("64_CH_SP_Airfield_16")
			createPlayerSpawnPoint(101, (406.926, 103.713, -375.883), (0, 0, 0), True, 8)
			createSpawnPoint(101, (406.926, 103.713, -375.883), (0, 0, 0), True, 10)
			createSpawnPoint(101, (379.467, 103.259, -400.856), (0, 0, 0), True, 10)
			createSpawnPoint(101, (394.196, 101.018, -307.109), (0, 0, 0), True, 10)
			g_params['force_win'] = side
			game.common.sayall("Single player layout loaded")

	elif host.sgl_getMapName() == "beirut" and not oneplayer:
		bf2.gameLogic.setTickets(2, 9999)
		g_params['force_win'] = side

	elif host.sgl_getMapName() == "fall_of_tobruk" and mapinfo.size == 64:
		if not oneplayer:
			bf2.gameLogic.setTickets(2, 9999)
			g_params['force_win'] = side

	elif host.sgl_getMapName() == "tunis_1943" and mapinfo.size in [16,64]:
		LMS_MODE = True
		COMMANDER_RESTRICTED = True
		if not oneplayer:
			bf2.gameLogic.setTickets(1, 9999)
			g_params['force_win'] = side

	elif host.sgl_getMapName() == "Gulf_Of_OmanHD_2017":
		if oneplayer:
			for vehicle, vehicle_id in getObjectsOfTemplate("mec_ats_milan"):
				if vehicle.getPosition() != (0.0,0.0,0.0):
					try_destruct_vehicle(vehicle, vehicle_id)
			deleteSpawner("Olive_FieldCannon")
			deleteSpawner("RiverFort_FieldCannon")
			deleteSpawner("Rock_FieldCannon")
			game.common.sayall("Simplified layout loaded")

	elif host.sgl_getMapName() in ["AIX_Operation_Static","albasrah_2","battle_of_brest","Devils_Perch_Day","eppeldorf","falaise_pocket","fall_of_tobruk","gaza_2","Hangar_18","Last_Stand_Snipers","lebisey","Majidah_Hill","Mashtuur_City","port_en_bessin","Road_To_Jalalabad","seelow_coop","sharqi_peninsula","Strike_at_KarkandHD_2017","supercharge","Urban_Jungle"]:
		COMMANDER_RESTRICTED = True


def calcStartTickets(mapDefaultTickets):
	return int(mapDefaultTickets * (bf2.serverSettings.getTicketRatio() / 100.0))

	
def onTimeLimitReached(value):
	global g_params
	global ControlPoints
	forcewin = g_params.get('force_win', 0)
	side = g_params.get('side', 0)
	cp_found = False

	team1tickets = bf2.gameLogic.getTickets(1)
	team2tickets = bf2.gameLogic.getTickets(2)
	
	winner = 0
	victoryType = 0

	for key in ControlPoints:
		if ControlPoints[key][3] == int(side):
			cp_found = True
			break

	if forcewin != 0 and cp_found and host.timer_getWallTime() - g_params.get('start_time',0) > g_params.get('timelimit', 3600) - 30: 
		winner = forcewin
		victoryType = 3
	else:
		if team1tickets > team2tickets:
			winner = 1
			victoryType = 3
		elif team2tickets > team1tickets:
			winner = 2
			victoryType = 3
	
	host.sgl_endGame(winner, victoryType)


def onPlayerDeath(victim, vehicle):
	global ControlPoints
	global g_params
	global LMS_MODE

	if not victim:
		return

	side = g_params.get('side', 0)
	victim.score.deaths += 1

	if victim and not victim.isAIPlayer():
		heal_loop = getattr(victim, 'hp', [200, 200, None, None, False])[3]
		monitor_loop = getattr(victim, 'health_monitor', [None, False])[0]
		if heal_loop:
			heal_loop.abort()
			heal_loop = None

		if monitor_loop:
			monitor_loop.abort()
			monitor_loop = None

	if LMS_MODE and not (victim.isAIPlayer() and victim.getTeam() == side) and (bf2.gameLogic.getTickets(1) == 0 or bf2.gameLogic.getTickets(2) == 0):
		alive_team1 = [x for x in bf2.playerManager.getPlayers() if x.getTeam() == 1 and x.isAlive() and not x.isManDown() and (getVehicleType(bf2.objectManager.getRootParent(x.getVehicle()).templateName.lower()) in [0,1,3,4,7,8] or not x.isAIPlayer())]
		alive_team2 = [x for x in bf2.playerManager.getPlayers() if x.getTeam() == 2 and x.isAlive() and not x.isManDown() and (getVehicleType(bf2.objectManager.getRootParent(x.getVehicle()).templateName.lower()) in [0,1,3,4,7,8] or not x.isAIPlayer())]
		if not (alive_team1 and alive_team2):
			host.sgl_endGame((1,2)[len(alive_team1) == 0], 3)
		return

	team = victim.getTeam()
	teamTickets = bf2.gameLogic.getTickets(team)
	teamTickets -= 1
	bf2.gameLogic.setTickets(team, teamTickets)
	foundLivingHuman = False
	foundActiveCP = False
	foundLivingPlayer = False
	foundLivingEnemy = False
	if victim and not victim.isAIPlayer():
		for p in bf2.playerManager.getPlayers():
			if not p.isAIPlayer() and p.isAlive():
				foundLivingHuman = True
				break
		if not foundLivingHuman:
			for key in ControlPoints:
				if ControlPoints[key][3] in [0, side] and not (key.lower() in ["cp_32_roundender","CP_Sector1"] or "dummy" in key.lower()):
					foundActiveCP = True
					break
	
			if side in [1,2] and not foundActiveCP:
				winner = 0
				if (victim.getTeam() == 1):
					winner = 2
				else:
					winner = 1
				bf2.gameLogic.setTicketState(1, 0)
				bf2.gameLogic.setTicketState(2, 0)
				host.sgl_endGame(winner, 3)

	elif team != side:
		# check if it was the last AI player and there are no active CPs to spawn
		for p in bf2.playerManager.getPlayers():
			if not foundLivingEnemy and p != victim and p.getTeam() != side and p.isAlive() and getVehicleType(bf2.objectManager.getRootParent(p.getVehicle()).templateName.lower()) == 8:
				foundLivingEnemy = True
				return

			updateTicketLoss()

		for key in ControlPoints:
			if not ControlPoints[key][3] in [side] and not (key.lower() in ["cp_32_roundender","CP_Sector1"] or "dummy" in key.lower()):
				foundActiveCP = True
				break

		if not foundLivingEnemy and not foundActiveCP:
			bf2.gameLogic.setTicketState(1, 0)
			bf2.gameLogic.setTicketState(2, 0)
			host.sgl_endGame(side, 3)

	if victim and victim.isAIPlayer():
		if victim.getName() == "Fred Orfoe":
			oldside = victim.getTeam()
			victim.setTeam(3 - oldside)


def onPlayerKilled(victim, attacker, weapon, assists, object):
	if not victim: 
		return
	victim.killed = True

	if victim and not victim.isAIPlayer():

		cheats = getattr(player, 'cheats', [])
		if "iddqd" in cheats:
			heal_loop = getattr(victim, 'iddqd', None)
		else:
			heal_loop = getattr(victim, 'hp', [200, 200, None, None, False])[3]
		if heal_loop:
			heal_loop.abort()
			heal_loop = None

	# update flag takeover status if victim was in a CP radius
	cp = getOccupyingCP(victim)
	vehicle = bf2.objectManager.getRootParent(victim.getVehicle())
	if cp:
		onCPTrigger(-1, cp, vehicle, False, None)

		# give defend score if killing enemy within cp radius
		if cp != None and attacker != None and cp.cp_getParam('unableToChangeTeam') == 0 and cp.cp_getParam('onlyTakeableByTeam') == 0:
			if attacker.getTeam() != victim.getTeam():
				if cp.cp_getParam('team') == attacker.getTeam():
					attacker.score.cpDefends += 1
					addScore(attacker, SCORE_DEFEND, RPL)
					bf2.gameLogic.sendGameEvent(attacker, 12, 1) #12 = Conquest, 1 = Defend
			else:
				if cp.cp_getParam('team') != attacker.getTeam() and not victim.isAIPlayer():
					addScore(attacker, -10, RPL)
					

# update ticket system
def updateTicketLoss():
	global LMS_MODE
	# we stop the ticket loss during LMS mode
	if LMS_MODE and (bf2.gameLogic.getTickets(1) == 0 or bf2.gameLogic.getTickets(2) == 0):
		return

	areaValueTeam1 = 0
	areaValueTeam2 = 0
	totalAreaValue = 0
	numCpsTeam0 = 0
	numCpsTeam1 = 0
	numCpsTeam2 = 0
	global ControlPoints
	
	# calculate control point area value for each team
	for key in ControlPoints:
		team = ControlPoints[key][3]
		obj = ControlPoints[key][0]
		if team == 1:
			areaValueTeam1 += obj.cp_getParam('areaValue', team)
			totalAreaValue += areaValueTeam1
			numCpsTeam1 += 1
		elif team == 2:
			areaValueTeam2 += obj.cp_getParam('areaValue', team)
			totalAreaValue += areaValueTeam2
			numCpsTeam2 += 1
		else:
			numCpsTeam0 += 1
			totalAreaValue += 0
		
	# check if a team has no control points
	if numCpsTeam1 == 0 or numCpsTeam2 == 0:
		if numCpsTeam1 == 0:
			losingTeam = 1
			winningTeam = 2
		else:
			losingTeam = 2
			winningTeam = 1
		
		# check if there is anyone alive
		foundLivingPlayer = False
		for p in bf2.playerManager.getPlayers():
			if p.getTeam() == losingTeam and p.isAlive():
				foundLivingPlayer = True
				break
				
		if not foundLivingPlayer:

			# drop tickets
			ticketLossPerSecond = bf2.gameLogic.getDefaultTicketLossAtEndPerMin()
			bf2.gameLogic.setTicketChangePerSecond(losingTeam, -ticketLossPerSecond)
			bf2.gameLogic.setTicketChangePerSecond(winningTeam, 0)
			
			return

	
	# update ticket loss
	team1AreaOverweight = areaValueTeam1 - areaValueTeam2
	percentualOverweight = 1.0
	if totalAreaValue != 0:
		percentualOverweight = abs(team1AreaOverweight / totalAreaValue)
	
	ticketLossPerSecTeam1 = calcTicketLossForTeam(1, areaValueTeam2, -team1AreaOverweight)
	ticketLossPerSecTeam2 = calcTicketLossForTeam(2, areaValueTeam1, team1AreaOverweight)
	bf2.gameLogic.setTicketChangePerSecond(1, -ticketLossPerSecTeam1)
	bf2.gameLogic.setTicketChangePerSecond(2, -ticketLossPerSecTeam2)


# actual ticket loss calculation function
def calcTicketLossForTeam(team, otherTeamAreaValue, otherTeamAreaOverweight):
	if otherTeamAreaValue >= 100 and otherTeamAreaOverweight > 0:
		ticketLossPerSecond = (bf2.gameLogic.getDefaultTicketLossPerMin(team) / 60.0) * (otherTeamAreaOverweight / 100.0)
		return ticketLossPerSecond
	else:
		return 0


# called when tickets reach a predetermined limit (negativ value means that the tickets have become less than the limit)
def onTicketLimitReached(team, limitId):
	global LMS_MODE
	global SpawnPoints
	if host.timer_getWallTime() - g_params.get('start_time',0) > 600 and limitId == -1:
		if LMS_MODE:
			game.common.sayall('\xa73\xa7c1001Last man standing mode activated\xa73\xa7c1001')
			bf2.gameLogic.setTicketChangePerSecond(1, 0)
			bf2.gameLogic.setTicketChangePerSecond(2, 0)
			bf2.gameLogic.setTickets(1, 0)
			bf2.gameLogic.setTickets(2, 0)

			for sp_id in SpawnPoints.values():
				rconExec('object.active id%d' % int(sp_id))
				rconExec('object.delete')
			SpawnPoints.clear()
	
			for rally in bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.PlayerControlObject'):
				if (str(rally.templateName).lower())[0:15] == "rallypoint_hand" and rally.getPosition() != (0.0,0.0,0.0):
					out = getObjectsOfTemplate(rally.templateName)
					try_destruct_vehicle(out[-1][0], out[-1][1])
		else:
			if limitId == -1:
				winner = int(3 - team)
				
				bf2.gameLogic.setTicketState(1, 0)
				bf2.gameLogic.setTicketState(2, 0)
			
				host.sgl_endGame(winner, 3)		
		
			# update ticket state
			else:
				updateTicketWarning(team, limitId)


# called when the ticket state should be updated (for triggering messages and sounds based on tickets left)
def updateTicketWarning(team, limitId):

	oldTicketState = bf2.gameLogic.getTicketState(team)
	newTicketState = 0
	
	if (oldTicketState >= 10):
		newTicketState = 10		

	if (limitId == -2):
		newTicketState = 10
	
	elif (limitId == 2):
		newTicketState = 0		

	elif (limitId == -3):
		newTicketState += 2

	elif (limitId == -4):
		newTicketState += 1

	if (oldTicketState != newTicketState):
		bf2.gameLogic.setTicketState(team, newTicketState)
		
	
	
# called when someone enters or exits cp radius
def onCPTrigger(triggerId, cp, vehicle, enter, userData):

#	message = ("Called at: " + str(host.timer_getWallTime()) + ", side: " + str(ControlPoints[cp.templateName][3]) + ", enter: " + str([triggerId, cp, vehicle, enter, userData]))
#	if cp.templateName == "CP_16_tunis_old_town_entr":
#		print(message)

	if getVehicleType(vehicle.templateName) == 1:
		return

	global ControlPoints
	if not cp.isValid(): return
	
	if vehicle and vehicle.getParent(): return
	
	# can this cp be captured at all?
	if cp.cp_getParam('unableToChangeTeam') != 0:
		return					
	cpTeam = cp.cp_getParam('team')
		
	playersInVehicle = None	
	if vehicle:
		playersInVehicle = vehicle.getOccupyingPlayers()
	
	if enter:
		for p in playersInVehicle:
			cp = getOccupyingCP(p)
			if cp:
				if not p.getIsInsideCP():
					if g_debug: print("Resetting enterPctAt for player ", p.getName())
					p.enterCpAt = host.timer_getWallTime()
	
	if vehicle:	
		for p in playersInVehicle:
			# only count first player in a vehicle
			if p == playersInVehicle[0]:  
				if g_debug: print(p.index, " is in radius. v=", vehicle.templateName)
				p.setIsInsideCP(enter)
			else:
				p.setIsInsideCP(0)
				if enter:
					bf2.gameLogic.sendHudEvent(p, 66, 49) #66 = HEEnableHelpMessage, 49 = VHMExitToCaptureFlag;			

	# count people in radius
	team1Occupants = 0
	team2Occupants = 0

	pcos = bf2.triggerManager.getObjects(cp.triggerId)
	for o in pcos:
		if not o: continue # you can get None in the result tuple when the host can't figure out what object left the trigger
		if o.getParent(): continue # getOccupyingPlayers returns all players downwards in the hierarchy, so dont count them twice
		occupyingPlayers = o.getOccupyingPlayers()
		for p in occupyingPlayers:
			# only count first player in a vehicle
			if p != occupyingPlayers[0]: 
				continue
				
			if p.isAlive() and not p.isManDown() and not p.killed:				
				if not p.isAIPlayer() and int(cp.getTemplateProperty('minNrToTakeControl', 0)) > 1 and (not ControlPoints[cp.templateName][3] == int(p.getTeam()) or ControlPoints[cp.templateName][3] == 0) and not p.index in ControlPoints[cp.templateName][5]:
					nrstr = DIGITS.get(str(cp.getTemplateProperty('minNrToTakeControl', 2)),"uknown number")
					message = (str(p.getName()) + ", this CP needs " + nrstr + " or more players to capture")
					warned = ControlPoints[cp.templateName][5]
					warned.append(p.index)
					ControlPoints[cp.templateName][5] = warned
					say_to_player(message, p)
				if p.getTeam() == 1:
					team1Occupants += 1
					break
				elif p.getTeam() == 2:
					team2Occupants += 1
					break

	attackOverWeight = 0

	if team1Occupants > team2Occupants and team1Occupants >= int(cp.getTemplateProperty('minNrToTakeControl')):
		attackingTeam = 1

	elif team2Occupants > team1Occupants and team2Occupants >= int(cp.getTemplateProperty('minNrToTakeControl')):
		attackingTeam = 2
	else:
		attackingTeam = 0

	if attackingTeam == 0:
		attackingTeam = cpTeam # Needs for correct flag showing while CP is in neutral status
		if team1Occupants == 0 and team2Occupants == 0:
			if cpTeam == 0:
				attackOverWeight = -0.5

			else:
				attackOverWeight = 0.5

	else:
		if cp.cp_getParam('flag') == attackingTeam or (cp.flagPosition == BOTTOM and cp.cp_getParam('team') == 0):
			attackOverWeight = abs(team1Occupants - team2Occupants)

		else:
			attackOverWeight = -abs(team1Occupants - team2Occupants)

	timeToChangeControl = [cp.cp_getParam('timeToGetControl'), cp.cp_getParam('timeToLoseControl')][attackOverWeight < 0]

	if cp.cp_getParam('onlyTakeableByTeam') != 0 and cp.cp_getParam('onlyTakeableByTeam') != attackingTeam:
		return
		print("Exiting at CP")


	# flag can only be changed when at bottom
	if cp.flagPosition == BOTTOM:
		cp.cp_setParam('flag', attackingTeam)


	# calculate flag raising/lowering speed
	if timeToChangeControl > 0:
		takeOverChangePerSecond = 1.0 * attackOverWeight / timeToChangeControl
	else:
		takeOverChangePerSecond = 0.0

	if (cp.flagPosition == TOP and takeOverChangePerSecond > 0) or (cp.flagPosition == BOTTOM and takeOverChangePerSecond < 0):
		takeOverChangePerSecond = 0.0

	if abs(takeOverChangePerSecond) > 0:
		cp.flagPosition = MIDDLE
				
	cp.cp_setParam('takeOverChangePerSecond', takeOverChangePerSecond)
#	message = ("Called at: " + str(host.timer_getWallTime()) + ', takeOverChangePerSecond: ' + str(takeOverChangePerSecond) + ', timeToChangeControl: ' + str(timeToChangeControl) + ', attackOverWeight: ' + str(attackOverWeight) + ', attackingTeam: ' + str(attackingTeam) + ', Team1occupants: ' + str(team1Occupants) + ', Team2occupants: ' + str(team2Occupants) + ", side: " + str(ControlPoints[cp.templateName][3]))
#	if cp.templateName == "CP_16_tunis_old_town_entr":
#		print(message)

			
	
# called when a control point flag reached top or bottom
def onCPStatusChange(cp, top):
	global ControlPoints
	global g_params
	global REINFORCEMENTS
	global kham_timer
	side = g_params.get('side',0)

	print(str(cp.templateName) + " status changed at " + str(host.timer_getWallTime()))

	if g_debug: print(str(cp.templateName) + " status changed")

	playerId = -1
	takeoverType = -1
	newTeam = -1
	scoringTeam = -1
	
	if top:	
		cp.flagPosition = TOP
	else:   
		cp.flagPosition = BOTTOM
	
	# determine capture / neutralize / defend

	if cp.cp_getParam('team') != 0:
		if top:
			# regained flag, do nothing
			pass
			
		else:
			# neutralize
			newTeam = 0
			if cp.cp_getParam('team') == 1:
				scoringTeam = 2
			else:
				scoringTeam = 1
				
			takeoverType = TAKEOVERTYPE_NEUTRALIZE

	else:

		if top:
			# capture
			newTeam = cp.cp_getParam('flag')
			scoringTeam = newTeam
			takeoverType = TAKEOVERTYPE_CAPTURE

		else:
			# hit bottom, but still neutral
			pass

	if newTeam != -1 and cp.cp_getParam('team') != newTeam:
		cp.cp_setParam('team', newTeam)
		ControlPoints[cp.templateName][3] = newTeam
	
	# scoring
	if takeoverType > 0:
		pcos = bf2.triggerManager.getObjects(cp.triggerId)
	
		# count number of players
		scoringPlayers = []
		firstPlayers = []
		for o in pcos:
			if o.getParent(): continue

			occupyingPlayers = o.getOccupyingPlayers()
			for p in occupyingPlayers:
				onCPTrigger(cp.triggerId, cp, bf2.objectManager.getRootParent(p.getVehicle()), 1, (1, 2, 3))
				# only count first player in a vehicle
				if p != occupyingPlayers[0]: 
					continue
					
				if p.isAlive() and not p.isManDown() and p.getTeam() == scoringTeam:
					if len(firstPlayers) == 0 or p.enterCpAt < firstPlayers[0].enterCpAt:
						firstPlayers = [p]
					elif p.enterCpAt == firstPlayers[0].enterCpAt:
						firstPlayers += [p]
					
					if not p in scoringPlayers:
						scoringPlayers += [p]
	
		# deal score
		for p in scoringPlayers:
			oldScore = p.score.score;
			if takeoverType == TAKEOVERTYPE_CAPTURE:
				if p in firstPlayers:
					p.score.cpCaptures += 1
					addScore(p, SCORE_CAPTURE, RPL)
					bf2.gameLogic.sendGameEvent(p, 12, 0) #12 = Conquest, 0 = Capture
					playerId = p.index
				else:
					p.score.cpAssists += 1
					addScore(p, SCORE_CAPTUREASSIST, RPL)
					bf2.gameLogic.sendGameEvent(p, 12, 2) #12 = Conquest, 2 = Assist


			elif takeoverType == TAKEOVERTYPE_NEUTRALIZE:
				if p in firstPlayers:
					p.score.cpNeutralizes += 1
					addScore(p, SCORE_NEUTRALIZE, RPL)
					bf2.gameLogic.sendGameEvent(p, 12, 3) #12 = Conquest, 3 = Neutralize
				else:
					p.score.cpNeutralizeAssists += 1
					addScore(p, SCORE_NEUTRALIZEASSIST, RPL)
					bf2.gameLogic.sendGameEvent(p, 12, 4) #12 = Conquest, 4 = Neutralize assist
					

	# immediate ticket loss for opposite team
	enemyTicketLossInstant = cp.cp_getParam('enemyTicketLossWhenCaptured')
	if enemyTicketLossInstant > 0 and newTeam > 0:
		
		if newTeam == 1:
			punishedTeam = 2
		elif newTeam == 2:
			punishedTeam = 1
		
		tickets = bf2.gameLogic.getTickets(punishedTeam)
		tickets -= enemyTicketLossInstant
		bf2.gameLogic.setTickets(punishedTeam, tickets)
	
	
	# update control point	
	cp.cp_setParam('playerId', playerId) #always set player first

#	print(str(cp.templateName) + " status change passed at " + str(host.timer_getWallTime()))	

	updateTicketLoss()

	foundLivingHuman = False
	foundActiveCP = False
	for p in bf2.playerManager.getPlayers():
		if not p.isAIPlayer() and p.isAlive():
			foundLivingHuman = True
			break
	if not foundLivingHuman:
		for key in ControlPoints:
			if ControlPoints[key][3] in [0, int(side)]:
				foundActiveCP = True
				break

		if side in [1,2] and not foundActiveCP:
			winner = newTeam
			bf2.gameLogic.setTicketState(1, 0)
			bf2.gameLogic.setTicketState(2, 0)
			host.sgl_endGame(winner, 3)

	if host.sgl_getMapName() == "gazala":
		if not REINFORCEMENTS and ControlPoints['CP_64_Gazala_SidiMuftan'][3] == 2 and ControlPoints['CP_64_Gazala_150thBox'][3] == 2:
			REINFORCEMENTS = True
			createSpawner("mbt_t80bv", 302, 1, (846.340, 29.823, -91.529), (0, 0, 0))
			game.common.sayall("Tank reinforcements have been arrived")

	if host.sgl_getMapName() == "mareth_line":
		if not REINFORCEMENTS and (ControlPoints['CP_64_mareth_Mareth'][3] == 2 or ControlPoints['CP_64_mareth_Toujane'][3] == 2):
			REINFORCEMENTS = True
			createSpawner("mbt_t80bv", 1, 1, (-425.511, 20.6062, 680.808), (80, 0, 0))
			createSpawner("mbt_t80bv_alt", 1, 1, (-438.236, 20.7284, 679.613), (80, 0, 0))
			createPlayerSpawnPoint(1, (-425.511, 20.6062, 680.808), (0, 0, 0), True, 2)
			createPlayerSpawnPoint(1, (-438.236, 20.7284, 679.613), (0, 0, 0), True, 2)
			game.common.sayall("Tank reinforcements have been arrived")

	if host.sgl_getMapName() == "khamisiyah":
		if not REINFORCEMENTS and (ControlPoints['cpname_khamisiyah_coop64_southkhidi'][3] == 2 or ControlPoints['cpname_khamisiyah_coop64_northkhidir'][3] == 2):
			kham_timer = loop(30, kham_failsafe, None)
			REINFORCEMENTS = True
			createSpawner("rutnk_t90a", 6, 1, (-1677.59, 40.001, 1892.85), (180, 0, 0))
			createSpawner("mbt_t80bv", 6, 1, (-1672.13, 40.001, 1892.97), (180, 0, 0))
			createSpawner("ru_ahe_havoc_sp", 6, 1, (-1704.689, 40.001, 1946.667), (180, 0, 0))
			game.common.sayall("Heavy reinforcements have been arrived")

		if ControlPoints['cpname_khamisiyah_coop64_chemfacil'][3] == 1 and not ControlPoints['cpname_khamisiyah_coop64_chemfacil'][6]:
			ControlPoints['cpname_khamisiyah_coop64_chemfacil'][6] = True
			createSpawnPoint(2, (214.476, 40.4348, 368.19), (0, 0, 0), False, None)
			createSpawnPoint(2, (220.698, 35.0022, 524.801), (0, 0, 0), False, None)
			createSpawnPoint(2, (403.524, 40.2039, 548.838), (0, 0, 0), False, None)
			createSpawner("deployable_tow_sp", 2, 2, (119.024, 40.3484, 445.865), (270, 0, 0))
			createSpawner("sam_tigercat", 2, 2, (134.451, 41.5183, 539.716), (270, 0, 0))
			createSpawner("usaav_m6", 2, 2, (1562.247, 38.004, 46.975), (-20, 0, 0), 240)
			createSpawner("us_tnk_m1a2", 2, 2, (1553.9, 38.0036, 80.729), (-109.826, 0, 0), 120)
			createSpawner("us_tnk_m1a2", 2, 2, (1584.56, 38.0036, 92.0098), (-109.826, 0, 0), 120)
			createSpawnPoint(2, (119.024, 40.3484, 445.865), (0, 0, 0), True, None)
			createSpawnPoint(2, (134.451, 41.5183, 539.716), (0, 0, 0), True, None)

	if host.sgl_getMapName() == "sidi_bou_zid":
		mapinfo = game.maplist.getCurrentMapInfo()
		if mapinfo.size == 64:
			if not REINFORCEMENTS and (ControlPoints['CP_64_SidiBouZid_SidiBouZid'][3] == 1 and ControlPoints['CP_64_SidiBouZid_PosteDeLessouda'][3] == 1 and ControlPoints['CP_64_SidiBouZid_Outpost'][3] == 1):
				REINFORCEMENTS = True
				createSpawner("rutnk_t90a", 104, 1, (130.725, 25.853, -1.424), (76.469, 0, 0), 720)
				createSpawner("mbt_t80bv", 103, 1, (216.024, 25.820, -50.123), (-83, 0, 0), 720)
				game.common.sayall("Tank reinforcements have been arrived")


def onPlayerChangeWeapon(player, oldWeapon, newWeapon):
	if not player.isAIPlayer(): 
#		game.common.sayall(str(newWeapon.templateName))
		if (newWeapon.templateName).lower()[0:9] == "rallydrop":
			g_rally = bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.PlayerControlObject')
			count_rally = 0
			for rally in g_rally:
				if (str(rally.templateName).lower())[0:15] == "rallypoint_hand" and rally.getPosition() != (0.0,0.0,0.0):
					count_rally += 1
					if count_rally > 5:
						message = ("There are " + str(count_rally) + " rally points already in game, only 6 can work at the same time")
						game.common.sayall(message)
		if (newWeapon.templateName).lower()[0:14] == "fgm148_javelin":
			message = ("Attention: don't try to use FGM-148 with friendly vehicles are in sight")
			say_to_player(message, player)


def onPlayerRevived(victim, attacker):
	try:
		vehicle = victim.getVehicle()
		rootVehicle = bf2.objectManager.getRootParent(vehicle)
		VehicleName = rootVehicle.templateName
		rootVehicle.setDamage(25)

	except:
		pass

	# update flag takeover status if victim was in a CP radius
	victim.killed = False

	if victim and not victim.isAIPlayer(): 
		max_health, prev_health, last_damage_time, heal_loop, player_revived = getattr(victim, 'hp', [200, 200, None, None, False])
		setattr(victim, 'hp', [max_health, prev_health, last_damage_time, heal_loop, True])
#		game.common.sayall("Player revived")
	
	cp = getOccupyingCP(victim)
	if cp != None:
		onCPTrigger(-1, cp, bf2.objectManager.getRootParent(victim.getVehicle()), True, None)


def timerHandler(player):
	rconExec("physics.gravity 9")


def restartmap(time):
	global g_params
	mapinfo = game.maplist.getCurrentMapInfo()
	oneplayer = g_params.get('oneplayer', False)
	restarted = g_params.get('restarted', False)
	timelimit = g_params.get('timelimit', 0)
	start_time = g_params.get('start_time', 0)

	if not restarted:
		g_params['restarted'] = True
		rconExec('sv.timeLimit %s' % str(timelimit + start_time - 60))


def onPlayerSpawn(player, soldier):
	player.killed = False
	global g_params
	oneplayer = g_params.get('oneplayer', False)
	mapinfo = game.maplist.getCurrentMapInfo()
	if not player.isAIPlayer():
		body = player.getDefaultVehicle()
		setattr(player, 'hp', [body.getDamage(), body.getDamage(), None, None, False])
		monitor_loop = loop(1.2, player_health_monitor, player)
		setattr(player, 'health_monitor', [monitor_loop, False])
		if not g_params.get('init_done', False):
			g_params['init_done'] = True
			restartmap(host.timer_getWallTime())
			if not g_params.get('mapinit_done', False):
				mapinit()
			#New spawn points. Needs to be added only after the very first player spawn, as it is timer-based
			if mapinfo.name_lower == "warlord" and mapinfo.size == 32 and oneplayer:
				timer.once(300, (createSpawnPoint(6, (154.283, 98.4552, -45.8446), (-90, 0, 0), False, 1, 360)), None)
				timer.once(420, (createSpawnPoint(6, (-49.5896, 98.4552, -12.2632), (90, 0, 0), False, 1, 360)), None)

		if g_params.get('oneplayer', True) and not hasattr(player, 'hasreadinstruction'):
			bf2.Timer(timerHandler, 10, 1, player)
			message = ('\xa73\xa7c1001' + str(player.getName()) + ', PLEASE FOLLOW THE INSTRUCTION!' + '\xa73\xa7c1001')
			say_to_player(message, player)

	if mapinfo.name_lower == "mareth_line" and mapinfo.size == 64:
		specops_set = ["NATO_Specops","NATO_Specops_alt"]
		specops = specops_set[randint(0, len(specops_set) - 1)]
		rconExec('gameLogic.setKit 2 0 %s "usa_specops_soldier"' % specops)
		sniper_set = ["NATO_Sniper_tobruk","NATO_Sniper_M40","Sniper_US_M24","Sniper_US_M24","Sniper_US_M24"]
		sniper = sniper_set[randint(0, len(sniper_set) - 1)]
		rconExec('gameLogic.setKit 2 1 %s "usa_sniper_soldier"' % sniper)
		assault_set = ["NATO_Assault_alt","NATO_Assault"]
		assault = assault_set[randint(0, len(assault_set) - 1)]
		rconExec('gameLogic.setKit 2 2 %s "us_assault_soldier_bf3"' % assault)
		support_set = ["NATO_Support","Support_US_M249","NATO_Support_elcan","NATO_Support_m249","NATO_Support_m249"]
		support = support_set[randint(0, len(support_set) - 1)]
		rconExec('gameLogic.setKit 2 6 %s "usa_support_soldier"' % support)

	if mapinfo.name_lower == "fushe_pass" and mapinfo.size == 32:
		at_set = ["UN_AT","UN_AT","UN_AT","UN_AT_ATGM"]
		at = at_set[randint(0, len(at_set) - 1)]
		rconExec('gameLogic.setKit 1 6 %s "un_at_soldier"' % at)

	if mapinfo.name_lower == "sidi_bou_zid" and mapinfo.size == 64:
		at_list = [True for x in bf2.playerManager.getPlayers() if (x.isAlive() and x.getTeam() == 2 and x.getKit().templateName in ["ISIS_AT","ISIS_AT","ISIS_AT_AA"])]
		at_set = (["ISIS_AT","ISIS_AT","ISIS_AT_AA"],["ISIS_Assault_aa","ISIS_Assault_inf"])[len(at_list) > 6]
		at = at_set[randint(0, len(at_set) - 1)]
		rconExec('gameLogic.setKit 2 6 %s "isis_at_soldier"' % at)

	if mapinfo.name_lower == "kashan_desert" and mapinfo.size == 32:
		at_set = ["ISIS_AT","ISIS_AT","ISIS_AT_T"]
		at = at_set[randint(0, len(at_set) - 1)]
		rconExec('gameLogic.setKit 2 6 %s "isis_at_soldier"' % at)

	if mapinfo.name_lower == "supercharge":
		at_list = [True for x in bf2.playerManager.getPlayers() if (x.isAlive() and x.getTeam() == 1 and x.getKit().templateName in ["ISIS_AT","ISIS_AT","ISIS_AT_AA"])]
		at_set = (["ISIS_AT","ISIS_AT","ISIS_AT_AA"],["ISIS_Assault_aa","ISIS_Assault_inf"])[len(at_list) > 5]
		at = at_set[randint(0, len(at_set) - 1)]
		rconExec('gameLogic.setKit 1 6 %s "isis_at_soldier"' % at)

	if mapinfo.name_lower in ["khamisiyah","muttrah_city_2"] or (mapinfo.name_lower == "siege_of_tobruk" and mapinfo.size == 32):
		specops_set = ["NATO_Specops","NATO_Specops_alt"]
		specops = specops_set[randint(0, len(specops_set) - 1)]
		rconExec('gameLogic.setKit 2 0 %s "us_specops_soldier"' % specops)
		sniper_set = ["NATO_Sniper_tobruk","NATO_Sniper_M40","Sniper_US_M24","Sniper_US_M24","Sniper_US_M24"]
		sniper = sniper_set[randint(0, len(sniper_set) - 1)]
		rconExec('gameLogic.setKit 2 1 %s "us_sniper_soldier"' % sniper)
		assault_set = ["NATO_Assault_alt","NATO_Assault"]
		assault = assault_set[randint(0, len(assault_set) - 1)]
		rconExec('gameLogic.setKit 2 2 %s "us_assault_soldier_bf3"' % assault)
		support_set = ["NATO_Support","Support_US_M249","NATO_Support_elcan","NATO_Support_m249","NATO_Support_m249"]
		support = support_set[randint(0, len(support_set) - 1)]
		rconExec('gameLogic.setKit 2 3 %s "us_support_soldier"' % support)
		# AT units limiting
		at_list = [True for x in bf2.playerManager.getPlayers() if (x.isAlive() and x.getTeam() == 2 and x.getKit().templateName in ["NATO_AT","NATO_AT_kham","NATO_AT_predator","NATO_AT"])]
		at_set = (["NATO_AT","NATO_AT_kham","NATO_AT_predator","NATO_AT"],["NATO_Assault_alt","NATO_Assault"])[len(at_list) > 10]
		at = at_set[randint(0, len(at_set) - 1)]
		rconExec('gameLogic.setKit 2 6 %s "us_at_soldier"' % at)



def arty_scan(player):
	global ArtyLoop
	vehicle = bf2.objectManager.getRootParent(player.getVehicle())
	if vehicle.templateName != 'sf14_periscope':
		ArtyLoop.abort()
		ArtyLoop = None
		return
	array = host.omgr_getObjectsOfTemplate('art_pco')

	if len(array):
		for element in array:
			position = element.getPosition()
			if position != (0.0, 0.0, 0.0):
				game.common.sayall("Mortar barrage confirmed")
				ArtyLoop.abort()
				ArtyLoop = None
				timer.once(35, spawnArtyAt, position, 5)
				if vehicle.templateName == 'sf14_periscope': 
					timer.once(40, loopTimer, player)
				return


def loopTimer(player):
	global ArtyLoop
	vehicle = bf2.objectManager.getRootParent(player.getVehicle())
	if not ArtyLoop and vehicle.templateName == 'sf14_periscope': 
		ArtyLoop = loop(4, arty_scan, player)

		
def onEnterVehicle(player, vehicle, freeSoldier=False):
	global REINFORCEMENTS
	if not player.isAIPlayer():
		if vehicle.templateName == 'sf14_periscope':
			loopTimer(player)
		elif vehicle.templateName == "fr_tnk_leclerc_bf2" and host.sgl_getMapName() == "kashan_desert" and not REINFORCEMENTS:
			createSpawner("rutnk_t90a", 7, 2, (-1131.3, 11, 955.8), (180, 0, 0), 600)
			createSpawner("rutnk_t90a", 7, 2, (-371.001, 16.3947, 667.352), (270, 0, 0), 600)
			REINFORCEMENTS = True

	player.setIsInsideCP(False)
	cp = getOccupyingCP(player)
	if cp:
		onCPTrigger(-1, cp, vehicle, False, None)
		updateCaptureStatus(vehicle)


def onExitVehicle(player, vehicle):
	# update flag takeover status if player in a CP radius
	if g_debug: print("Player exiting ", player.getName())
	cp = getOccupyingCP(player)
	# can this cp be captured at all?
	player.setIsInsideCP(cp != None and cp.cp_getParam('unableToChangeTeam') == 0)
	updateCaptureStatus(vehicle)
	

#Update cp capture status on players in vehicle
def updateCaptureStatus(vehicle):	

	rootVehicle = bf2.objectManager.getRootParent(vehicle)
	playersInVehicle = rootVehicle.getOccupyingPlayers()
	
	# set the player in the topmost pco as inside - others outside
	for p in playersInVehicle:
		if g_debug: print("Players in vehicle ", p.getName())
		cp = getOccupyingCP(p)
		p.setIsInsideCP(cp != None and cp.cp_getParam('unableToChangeTeam') == 0 and p == playersInVehicle[0])

		
# find cp that player is occupying, if any		
def getOccupyingCP(player):
	global ControlPoints
	vehicle = bf2.objectManager.getRootParent(player.getVehicle())
	playerPos = vehicle.getPosition()
	
	# find closest CP
	closestCP = None
	if len(ControlPoints) == 0: 
		return None

	for key in ControlPoints:
		obj = ControlPoints[key][0]
		distanceTo = getVectorDistance(playerPos, obj.getPosition())
		if closestCP == None or distanceTo < closestCPdist:
			closestCP = obj
			closestCPdist = distanceTo
	
	# is the player in radius?
	pcos = bf2.triggerManager.getObjects(closestCP.triggerId)
	for o in pcos:
		if o == player.getDefaultVehicle():
			# Player is DEFAULT vehicle - this is needed when called from onEnterVehicle
			return closestCP
		else:
			for p in o.getOccupyingPlayers():
				if p == player:
					return closestCP
	
	return None


def deleteSpawnpoint(spawner):
	tuples = getObjectsOfTemplate(spawner)
	print("Trying to delete spawnpoint: ", spawner)
	for k in range(len(tuples)):
		rconExec('object.active id%d' % int(tuples[k][1]))
		rconExec('object.delete')


def createSpawnPoint(cpid, pos, rot, enter=None, group=None, ttl=None):
	global SpawnPoints
	spawner = 'spw_' + str(pos[0])
	rconExec('ObjectTemplate.create SpawnPoint %s' % spawner)
	rconExec('ObjectTemplate.activeSafe SpawnPoint %s' % spawner)
	rconExec('ObjectTemplate.setControlPointId %s' % cpid)
	rconExec('ObjectTemplate.setScatterSpawnPositions 1')
	rconExec('ObjectTemplate.setSpawnPositionOffset 0/1.25/0')
	rconExec('ObjectTemplate.setOnlyForAI 1')
	rconExec('ObjectTemplate.setAllowSpawnCloseToVehicle 1')
	if enter:
		rconExec('ObjectTemplate.setAIEnterOnSpawn 1')
	
	if group:
		rconExec('ObjectTemplate.setGroup %s' % group)
	pos = '/'.join(map(lambda x: str(round(x,2)), pos))
	rot = '/'.join(map(lambda x: str(float(x)), rot))
	rconExec('Object.create %s' % spawner)
	rconExec('Object.absolutePosition %s' % pos)
	rconExec('Object.rotation %s' % rot)
	if ttl:
		bf2.Timer(deleteSpawnpoint, ttl, 1, spawner)
	else:
		SpawnPoints[spawner] = getObjectsOfTemplate(spawner)[0][1]


def createPlayerSpawnPoint(cpid, pos, rot, enter=False, group=None, ttl=None):
	spawner = 'spwp_' + str(pos[0])
	rconExec('ObjectTemplate.create SpawnPoint %s' % spawner)
	rconExec('ObjectTemplate.activeSafe SpawnPoint %s' % spawner)
	rconExec('ObjectTemplate.setControlPointId %s' % cpid)
	rconExec('ObjectTemplate.setScatterSpawnPositions 1')
	rconExec('ObjectTemplate.setSpawnPositionOffset 0/1.25/0')
	rconExec('ObjectTemplate.setOnlyForHuman 1')
	rconExec('ObjectTemplate.setAllowSpawnCloseToVehicle 1')
	if enter:
		rconExec('ObjectTemplate.setEnterOnSpawn 1')
	if group:
		rconExec('ObjectTemplate.setGroup %s' % group)
	pos = '/'.join(map(lambda x: str(round(x,2)), pos))
	rot = '/'.join(map(lambda x: str(float(x)), rot))
	rconExec('Object.create %s' % spawner)
	rconExec('Object.absolutePosition %s' % pos)
	rconExec('Object.rotation %s' % rot)
	if ttl:
		bf2.Timer(deleteSpawnpoint, ttl, 1, spawner)



def createSpawner(template, cpid, team, pos, rot, spawndelay=9999, delayed=False, maxnr=None):
	spawner = 'ospw_' + str(pos[0])
	print("Created spawner: " + str(template) + " at " + str(pos) + " with rot " + str(rot))
	rconExec('ObjectTemplate.create ObjectSpawner %s' % spawner)
	rconExec('ObjectTemplate.activeSafe ObjectSpawner %s' % spawner)
	rconExec('ObjectTemplate.hasMobilePhysics 0')
	rconExec('ObjectTemplate.setObjectTemplate %s %s' % (team, template))
	rconExec('ObjectTemplate.minSpawnDelay %s' % spawndelay)
	rconExec('ObjectTemplate.maxSpawnDelay %s' % spawndelay)
	if maxnr and not str(template) == "deployable_tow_sp":
		rconExec('ObjectTemplate.maxNrOfObjectSpawned %s' % maxnr)
	if team != 0:
		rconExec('ObjectTemplate.teamOnVehicle 1')
		if not str(template) == "deployable_tow_sp":
			rconExec('ObjectTemplate.team %s' % team)
	if delayed:
		rconExec('ObjectTemplate.spawnDelayAtStart 1')
	
	pos = '/'.join(map(lambda x: str(round(x,2)), pos))
	rot = '/'.join(map(lambda x: str(float(x)), rot))
	rconExec('Object.create %s' % spawner)
	rconExec('Object.absolutePosition %s' % pos)
	rconExec('Object.rotation %s' % rot)
	rconExec('Object.setControlPointId %s' % cpid)
	if spawndelay == 9999:
		rconExec('Object.delete')


def createKit(kit, cpid, team, pos, rot=(0, 0, 0)):
	spawner = 'kspw_' + str(pos[0])
	rconExec('ObjectTemplate.create ObjectSpawner %s' % spawner)
	rconExec('ObjectTemplate.activeSafe ObjectSpawner %s' % spawner)
	rconExec('ObjectTemplate.hasMobilePhysics 0')
	rconExec('ObjectTemplate.TimeToLive 1200')
	rconExec('ObjectTemplate.setObjectTemplate 0 %s' % kit)
	rconExec('ObjectTemplate.setObjectTemplate 1 %s' % kit)
	rconExec('ObjectTemplate.setObjectTemplate 2 %s' % kit)
	rconExec('ObjectTemplate.minSpawnDelay 9999')
	
	pos = '/'.join(map(lambda x: str(round(x,2)), pos))
	rot = '/'.join(map(lambda x: str(float(x)), rot))	
	rconExec('Object.create %s' % spawner)
	rconExec('Object.absolutePosition %s' % pos)
	rconExec('Object.rotation %s' % rot)
	rconExec('Object.setControlPointId %s' % cpid)
	rconExec('Object.delete')


def deleteSpawner(spawner):
	rconExec('ObjectTemplate.activeSafe ObjectSpawner %s' % spawner)
	rconExec('Object.activeSafe %s' % spawner)
	rconExec('Object.delete')


def bigOrangeText(s):
	return '\xa73\xa7c1001' + s + '\xa73\xa7c1001'


def active(t):
	rconExec('objecttemplate.active %s' % t)


def activeSafe(t, template):
	rconExec('objecttemplate.activesafe %s %s' % (t, template))

Airdrop = AirdropManager()

