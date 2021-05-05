import host
import bf2
import math
import types
from random import randint, random
from bf2 import g_debug
from bf2object import bf2object
from timer import timer
import game.common
from game.scoringCommon import say_to_player


#return a random deviation position
def rndDevPosition(position):
	r = random() * 70
	th = random() * 2 * math.pi
	x = (position[0] + r * math.cos(th))
	z = position[1] + 100.0 + (random() * 100.0)
	y = position[2] + r * math.sin(th)
	return (round(x, 2), round(z, 2), round(y, 2))


#use team artillery at position	
def spawnArtyAt(position, roundsLeft):
	if roundsLeft <= 0: 
		return	
	for i in range(4):
		pos = rndDevPosition(position)
		artySpw = bf2object('a_artillery_PCO', pos, True)
	timer.once(7, spawnArtyAt, position, roundsLeft - 1)


class AirdropManager:
	def __init__(self):
		self.settings = {
					"TEAM1_SUPPLYDROP_NAME" : "supply_crate",			#supply drop object name for team 1(mec,ch)
					"TEAM2_SUPPLYDROP_NAME" : "supply_crate",			#supply drop object name for team 2(us,eu)
					"SUPPLYDROP_INTERVAL" : 180.0,					#interval between supply drops
					"SUPPLYDROP_DEVIATION_RADIUS" : 5.0,				#max deviation of supply drops(in meters)
					"SUPPLYDROP_DEVIATION_RADIUS_MIN" : 2.0,			#min deviation of supply drops(in meters)(to avoid dropping directly at the soldier and crush him)
					"SUPPLYDROP_SPAWN_HEIGHT" : 100.0,				#how high the supply crate will be spawn(in meters)
					"VEHICLEDROP_INTERVAL" : 360.0,	
					"ARTILLERY_INTERVAL" : 120.0,	
					"ARTILLERY_NUMBER" : 5,	
					"SUPPLYDROP_NUMBER" : 5,					#number of supply crates available
					"VEHICLEDROP_NUMBER" : 5,					#number of vehicles available
					"VEHICLEDROP_DEVIATION_RADIUS" : 10.0,				#max deviation of vehicle drops(in meters)
					"VEHICLEDROP_DEVIATION_RADIUS_MIN" : 2.0,			#min deviation of vehicle drops(in meters)(to avoid dropping directly at the soldier and crush him)
					"VEHICLEDROP_SPAWN_HEIGHT" : 500.0				#how high the vehicle will be spawn(in meters)(too high will damage the vehicle)
				}
		self.supplydrop_number = self.settings["SUPPLYDROP_NUMBER"]
		self.vehicledrop_number = self.settings["VEHICLEDROP_NUMBER"]
		self.artillery_number = self.settings["ARTILLERY_NUMBER"]
		self.team1_supplydrop_ready = True
		self.team2_supplydrop_ready = True
		self.team1_vehicledrop_ready = True
		self.team2_vehicledrop_ready = True
		self.team1_artillery_ready = True
		self.team2_artillery_ready = True
		self.team1_vehicledrop_name = "drop_proxy"
		self.team2_vehicledrop_name = "drop_proxy"
		self.team1_lastartilleryTime = host.timer_getWallTime()
		self.team2_lastartilleryTime = host.timer_getWallTime()
		self.team1_lastSupplydropTime = host.timer_getWallTime()
		self.team2_lastSupplydropTime = host.timer_getWallTime()
		self.team1_lastVehicledropTime = host.timer_getWallTime()
		self.team2_lastVehicledropTime = host.timer_getWallTime()

	def disableArtillery(self, team):
		if team == 1: 
			self.team1_artillery_ready = False
			self.team1_lastartilleryTime = host.timer_getWallTime()
		elif team == 2: 
			self.team2_artillery_ready = False
			self.team2_lastartilleryTime = host.timer_getWallTime()
		timer.once(self.settings["ARTILLERY_INTERVAL"], self.enableArtillery, team)
		
	def enableArtillery(self, team):
		if team == 1: 
			self.team1_artillery_ready = True
		elif team == 2: 
			self.team2_artillery_ready = True
	
	#disable satellite for SUPPLYDROP_INTERVAL time
	def disableSupplydrop(self, team):
		if team == 1: 
			self.team1_supplydrop_ready = False
			self.team1_lastSupplydropTime = host.timer_getWallTime()
		elif team == 2: 
			self.team2_supplydrop_ready = False
			self.team2_lastSupplydropTime = host.timer_getWallTime()
		timer.once(self.settings["SUPPLYDROP_INTERVAL"], self.enableSupplydrop, team)
		
	def enableSupplydrop(self, team):
		if team == 1: 
			self.team1_supplydrop_ready = True
		elif team == 2: 
			self.team2_supplydrop_ready = True
	
	#disable satellite for SUPPLYDROP_INTERVAL time
	def disableVehicledrop(self, team):
		if team == 1: 
			self.team1_vehicledrop_ready = False
			self.team1_lastVehicledropTime = host.timer_getWallTime()
		elif team == 2: 
			self.team2_vehicledrop_ready = False
			self.team2_lastVehicledropTime = host.timer_getWallTime()
		timer.once(self.settings["VEHICLEDROP_INTERVAL"], self.enableVehicledrop, team)
		
	def enableVehicledrop(self, team):
		if team == 1: 
			self.team1_vehicledrop_ready = True
		elif team == 2: 
			self.team2_vehicledrop_ready = True
	
	def isSupplydropAvailable(self, team):
		if team == 1:
			return self.team1_supplydrop_ready
		elif team == 2:
			return self.team2_supplydrop_ready
		else:
			return False
	
	def isVehicledropAvailable(self, team):
		if team==1:
			return self.team1_vehicledrop_ready
		elif team==2:
			return self.team2_vehicledrop_ready
		else:
			return False

	def isArtilleryAvailable(self, team):
		if team==1:
			return self.team1_artillery_ready
		elif team==2:
			return self.team2_artillery_ready
		else:
			return False

	def startArtillery(self, team, position, player):
		if self.artillery_number <= 0:
			say_to_player("There are no artillery available", player)
			return False
		if not self.isArtilleryAvailable(team):
			say_to_player(("Artillery not available for " + str(int((max(self.team1_lastartilleryTime, self.team2_lastartilleryTime) + (self.settings["ARTILLERY_INTERVAL"]) - (host.timer_getWallTime())))) + " seconds"), player)
			return False
		timer.once(35, spawnArtyAt, position, 5)
		artyObj = bf2object("art_decoy", position, True)
		self.disableArtillery(team)
		self.artillery_number -= 1
		if self.artillery_number > 0:
			say_to_player(("Mortar barrage confirmed, mumber of artillery strikes available: " + str(self.artillery_number)), player)
		return True
	
	def startSupplydrop(self, team, position, player):
		if self.supplydrop_number <= 0:
			say_to_player("There are no supplies available", player)
			return False
		if not self.isSupplydropAvailable(team):
			say_to_player(("Supply drop not available for " + str(int((max(self.team1_lastSupplydropTime, self.team2_lastSupplydropTime) + (self.settings["SUPPLYDROP_INTERVAL"]) - (host.timer_getWallTime())))) + " seconds"), player)
			return False
		objName = (team==1) and self.settings["TEAM1_SUPPLYDROP_NAME"] or self.settings["TEAM2_SUPPLYDROP_NAME"]
		self.disableSupplydrop(team)
		newPos = self.rndPosition(position, self.settings["SUPPLYDROP_DEVIATION_RADIUS_MIN"], self.settings["SUPPLYDROP_DEVIATION_RADIUS"], self.settings["SUPPLYDROP_SPAWN_HEIGHT"])
		supplyObj = bf2object(objName, newPos, True)
		self.supplydrop_number -= 1
		if self.supplydrop_number > 0:
			say_to_player(("Supply drop coonfirmed, number of boxes available: " + str(self.supplydrop_number)), player)
		return True

	def startVehicledrop(self, team, position, player):
		if self.vehicledrop_number <= 0:
			say_to_player("There are no vehicles available", player)
			return False
		if not self.isVehicledropAvailable(team):
			say_to_player(("Vehicle drop not available for " + str(int((max(self.team1_lastVehicledropTime, self.team2_lastVehicledropTime) + (self.settings["VEHICLEDROP_INTERVAL"]) - (host.timer_getWallTime())))) + " seconds"), player)
			return False
		objName = (team==1) and self.team1_vehicledrop_name or self.team2_vehicledrop_name
		self.disableVehicledrop(team)
		newPos = self.rndPosition(position, self.settings["VEHICLEDROP_DEVIATION_RADIUS_MIN"], self.settings["VEHICLEDROP_DEVIATION_RADIUS"], self.settings["VEHICLEDROP_SPAWN_HEIGHT"])
		vehicleObj = bf2object(objName, newPos, True)
		self.vehicledrop_number -= 1
		if self.vehicledrop_number > 0:
			say_to_player(("Vehicle drop confirmed, number of vehicles available: " + str(self.vehicledrop_number)), player)
		return True
	
	#return a random deviation position
	def rndPosition(self, position, rndMin, rndMax, height):
		r = random() * (rndMax - rndMin) + rndMin
		th = random() * 2 * math.pi
		return (round(position[0] + r * math.cos(th),2), round(position[1] + height,2), round(position[2] + r * math.sin(th),2))
