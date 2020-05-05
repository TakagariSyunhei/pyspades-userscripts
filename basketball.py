#-*-coding:utf-8-*-
"""
ver1.0.0 (2015-06-21)
	Create:鷹狩俊平（twitter:@falcon9147)
	Beta

ver1.1.0 (2015-07-26)
	Author:鷹狩俊平（twitter:@falcon9147)
	Add  Throw-in and Own-Goal
	BugFix

ver1.2.0 (2015-08-18)
	Author:鷹狩俊平（twitter:@falcon9147)
	Add MakeGoal and SaveGoal function

ver1.2.1 (2017-02-19)
	Author:鷹狩俊平（twitter:@falcon9147)
	Add Timelimit for cancel Throw-in

ver1.3.1 (2020-05-05)
	Author:鷹狩俊平（twitter:@falcon9147)
	Add Spurt function


ゲームモードをバスケットボールにするスクリプト

アドミンコマンド
	/makegoal <team>
		ゴールの作成を行う。２つのブロックをスペードで叩くことでその間の立方体空間がゴールになる
		設定するチームはそのゴールを守るチームになる
	
	/savegoal
		作成したゴールをtxtファイルに記録する。
		<server.exeのフォルダ>/map/<マップ名>_goal.txt

設定方法
	コートサイズを変更する
		メタデータ「マップ名_goal.txt」の中の「noath_edga」、「south_edge」、「east_edge」と「west_edge」を書き換える
	スポーン座標を変更する
		メタデータ「マップ名_goal.txt」の中の「blue_spawn_pos」と「green_spawn_pos」を書き換える

----------------------------------------------------------------------------------------

Basketball
This script is for Basketball game

COMMANDS
	/makegoal <team>
		Start making goal by hitting blocks.
		The team, you choice defend the goal

	/savegoal
		Record the deta of goals
		<server.exe_path>/map/<map_name>_goal.txt

USAGE
	How to change coat size
		Overwrite the map-meta-deta [map name]_goal.txt
		'north_edge', 'south_edge', 'east_edge' and 'west_edge' mean coat size

	How to change spawn location
		Rewrite the map-meta-deta [map name]_goal.txt
		'blue_spawn_pos' and 'green_spawn_pos' mean spawn location
"""


import __builtin__
import json
import os
import math

from pyspades.constants import *
from pyspades.contained import BlockAction
from pyspades.server import block_action, orientation_data, grenade_packet, weapon_reload, set_tool, create_player
from pyspades.common import Vertex3, coordinates
from pyspades import world, contained
from pyspades.world import Grenade
from commands import add, admin, name, alias, join_arguments
from twisted.internet.reactor import callLater, seconds
from collections import defaultdict
from map import DEFAULT_LOAD_DIR



MESSAGE_THROW_IN = "!! Throw-in !!  {team} team's turn "

CENTER = (256, 256)
HIDE_POS = (0, 0, 63)

THROWIN_TIME = 20

SPURT_SPEED = 0.4


"""
	プレイヤーがインテルを持っていたらTrue、持っていなかったらFalseを返す
	check if the player has the intel
	
	@param holder : player
	@param flag : protocol.blue_team(/green_team).flag
	
	@return boolean
"""
def checkHolder(holder, flag):
	if flag.player == holder:
		return True
	else:
		return False

"""
	座標がコート内ならTrue、コート外ならFalseを返す
	check if the location is inside of Coat
	
	@param connection : player
	@param x,y : location
	
	@return boolean
"""
def checkCoatInside(connection, x, y):
	if connection.protocol.coat_edge_n < y and y < connection.protocol.coat_edge_s:
		if connection.protocol.coat_edge_w < x and x < connection.protocol.coat_edge_e:
			return True
	return False

"""
	スローインの時のインテルの出現位置を計算する
	Calcurate the location where the intel is going to spawns at throw-in mode
	
	@param connection : player who droped the intel
	@param x,y : location where the player dropped the intel
	
	@return x,y : location where the intel is going to spawns
"""
def calcOutsidePosition(connection, x, y):
	n_edge = connection.protocol.coat_edge_n
	s_edge = connection.protocol.coat_edge_s
	w_edge = connection.protocol.coat_edge_w
	e_edge = connection.protocol.coat_edge_e
	if y < n_edge:
		dy = n_edge - 1
	elif y > s_edge:
		dy = s_edge + 1
	else:
		dy = y
	
	if x < w_edge:
		dx = w_edge - 1
	elif x > e_edge:
		dx = e_edge + 1
	else:
		dx = x
	return (dx, dy)


"""
	スローインモードを理解できないプレイヤーが多いので追加した機能
	一定時間以上スローインモードが解除されない場合、インテルを中央に戻す
	
	New function added because a lot of player can't understand throw-in mode
	Reset throw-in mode and put intel at the center after throw-in mode contenued for long time
	
	@param connection : player who dropped the intel
	@param time : Remaining time to reset
"""
def game_reset_loop(connection, time):
	protocol = connection.protocol
	if protocol.mode_throwin:
		if time > 0:
			callLater(5, game_reset_loop, connection, time-5)
			msg = "!! " + str(time) + " sec to reset Throw-In mode !!"
			protocol.send_chat(msg)
			protocol.fog_flash(protocol.throwin_team.color)
		else:
			flag = protocol.throwin_team.other.flag
			if flag.player is not None:
				flag.player.drop_flag()
			position = (256, 256, 0)
			x = position[0]
			y = position[1]
			z = protocol.map.get_z(x, y, 60)
			flag.set(x, y, z)
			flag.update()
			flag = protocol.throwin_team.flag
			flag.set(x, y, z)
			flag.update()
			protocol.mode_throwin = False
			protocol.send_chat("!! Throw-In mode is Canceled !!")

"""
	オウンゴールした時に一瞬だけ相手チームに移る処理
	function to change the player's team temporarily when he/she scored own-goal
"""
def fill_create_player(player, team):
	x, y, z = player.world_object.position.get()
	create_player.x = x
	create_player.y = y
	create_player.z = z
	create_player.name = player.name
	create_player.player_id = player.player_id
	create_player.weapon = player.weapon
	create_player.team = team.id

"""
	作ったゴール情報を保存する
	register goal information
"""
@admin
def savegoal(connection):
	 connection.protocol.dump_goal_json()
	 connection.send_chat("!!GOAL SAVED!!")
	 return
add(savegoal)

"""
	ゴール作成モードに入る
	start goal-maing mode
"""
@admin
def makegoal(*arguments):
	connection = arguments[0]
	connection.reset_build()
	if connection.goal_making:
		connection.send_chat('Making goal is canceled')
	else:
		param = len(arguments)
		if param < 2:
			connection.send_chat('b = blue, g = green, n = neutral')
			connection.send_chat('Enter team')
			return False
		connection.arguments = arguments
		connection.send_chat('Hit 2 blocks to set goal area')
	connection.goal_making = not connection.goal_making
add(makegoal)

"""
	ゴールのデータを格納するクラス
	This class contains goal information
"""
class GoalObject:
	id = None
	label = None
	teamname = None

	def __init__(self, id_n, belong_team, x1, x2, y1, y2, z1, z2):
		self.id = id_n
		self.label = str(self.id)
		self.teamname = belong_team
		self.west = x1
		self.east = x2
		self.north = y1
		self.south = y2
		self.top = z1
		self.botom = z2


	def contains(self, x, y, z):
		if self.west <= x and self.east >= x:
			if self.north <= y and self.south >= y:
				if self.top <= z and self.botom >= z:
					return True
		return False

	def get_team(self):
		return self.teamname

	def serialize(self):
		return {
			'id' : self.id,
			'label' : self.label,
			'team' : self.teamname,
			'xpos' : (self.west, self.east),
			'ypos' : (self.north, self.south),
			'zpos' : (self.top, self.botom)
		}


def apply_script(protocol, connection, config):
	
	
	class BasketBallProtocol(protocol):
		coat_edge_n = None
		coat_edge_s = None
		coat_edge_w = None
		coat_edge_e = None
		highest_id = None
		goals = None
		goal_json_dirty = False
		autosave_loop = None
		callback = None
		blue_spawn_pos = None
		green_spawn_pos = None
		mode_throwin = False
		
		
		game_mode = CTF_MODE

		def on_map_change(self, map):
			self.flag_spawn_pos = CENTER
			self.mode_throwin = False
			self.throwin_team = None
			self.highest_id = -1
			self.goals = {}
			self.goal_json_dirty = False
			self.load_goal_json()
			if not self.coat_edge_n:
				self.coat_edge_n = 240
				self.coat_edge_s = 271
				self.coat_edge_w = 240
				self.coat_edge_e = 271
			if not self.blue_spawn_pos:
				self.blue_team.spawn_pos = (231, 255, 60)
				self.green_team.spawn_pos = (280, 256, 60)
			else:
				self.blue_team.spawn_pos = self.blue_spawn_pos
				self.green_team.spawn_pos = self.green_spawn_pos
		
		def bsk_flag_spawn(self, flag):
			z = self.map.get_z(self.flag_spawn_pos[0], self.flag_spawn_pos[1], 60)
			pos = (self.flag_spawn_pos[0], self.flag_spawn_pos[1], z)
			if flag is not None:
				flag.player = None
				flag.set(*pos)
				flag.update()
			return pos

		def bsk_reset_flags(self):
			self.bsk_flag_spawn(self.blue_team.flag)
			self.bsk_flag_spawn(self.green_team.flag)

		def on_game_end(self):
			self.flag_spawn_pos = CENTER
			self.bsk_reset_flags()
			return protocol.on_game_end(self)

		def on_flag_spawn(self, x, y, z, flag, entity_id):
			pos = self.bsk_flag_spawn(flag.team.other.flag)
			protocol.on_flag_spawn(self, pos[0], pos[1], pos[2], flag, entity_id)
			return pos

		def fog_flash(self, color):
			old_color = self.get_fog_color()
			self.set_fog_color(color)
			callLater(0.2, self.set_fog_color, old_color)
			
		def get_goal_json_path(self):
			filename = self.map_info.rot_info.full_name + '_goal.txt'
			return os.path.join(DEFAULT_LOAD_DIR, filename)


		def load_goal_json(self):
			path = self.get_goal_json_path()
			if not os.path.isfile(path):
				return
			with open(path, 'r') as file:
				data = json.load(file)
			ids =[]
			for goal_data in data['goals']:
				x1, x2 = goal_data['xpos']
				y1, y2 = goal_data['ypos']
				z1, z2 = goal_data['zpos']
				id = goal_data['id']
				teamname = goal_data['team']
				ids.append(id)
				goal = GoalObject(id, teamname, x1, x2, y1, y2, z1, z2)
				goal.label = goal_data['label']
				self.goals[id] = goal
			self.coat_edge_n = data['north_edge']
			self.coat_edge_s = data['south_edge']
			self.coat_edge_w = data['west_edge']
			self.coat_edge_e = data['east_edge']
			self.blue_spawn_pos = data['blue_spawn_pos']
			self.green_spawn_pos = data['green_spawn_pos']
			ids.sort()
			self.highest_id = ids[-1] if ids else -1
			self.goal_json_dirty = True

		def dump_goal_json(self):
			if(not self.goals and not self.goal_json_dirty):
				return
			data = {
				'goals' : [goal.serialize() for goal in self.goals.values()],
				'north_edge' : self.coat_edge_n,
				'south_edge' : self.coat_edge_s,
				'west_edge' : self.coat_edge_w,
				'east_edge' : self.coat_edge_e,
				'blue_spawn_pos' : self.blue_team.spawn_pos,
				'green_spawn_pos' : self.green_team.spawn_pos
			}
			path = self.get_goal_json_path()
			with open (path, 'w') as file:
				json.dump(data, file, indent = 4)
			self.goal_json_dirty = True

		def is_goal(self, x, y, z):
			for goal in self.goals.itervalues():
				if goal.contains(x, y, z):
					return goal
			return None
		
		"""
		スローインを宣言する
		Declare beginning of "Throw in"
		"""
		def declareThrowIn(self, team):
			self.send_chat("!! Throw In !!")
			
			if team == self.blue_team:
				callLater(2.0, self.blueTurn)
			else:
				callLater(2.0, self.greenTurn)
		    
		def blueTurn(self):
			self.send_chat("!! Blue Team has ball !!")
		
		def greenTurn(self):
			self.send_chat("!! Green Team has ball !!")

	class BasketBallConnection(connection):
		goal_making = False
		have_ball = False
		sneak = False
		scope = False
		damage_stock = 0.0
		regene = False


		def reset_build(self):
			self.block1_x = None
			self.block1_y = None
			self.block1_z = None
			self.block2_x = None
			self.block2_y = None
			self.block2_z = None
			self.block3_x = None
			self.block3_y = None
			self.block3_z = None
			self.arguments = None
			self.callback = None
			self.select = False
			self.points = None
			self.label = None
		
		"""
		HPを消費して高速で走る
		Consuming HP, run faster 
		"""
		def spurt(self):
			# ログアウト後にループ処理が残らないよう、存在の確認
			if isinstance(self.world_object, type(None)):
				return
				
			# 起動条件を確認して、座標を計算
			if self.sneak and self.scope:
				if self.hp < 2:
					self.send_chat("Out of Breath")
					return
				
				elif checkHolder(self, self.team.other.flag):
					self.send_chat("You can't dash with DRIBBLING")
					return
				
				else:
					x, y, z = self.world_object.position.get()
					ox, oy, oz = self.world_object.orientation.get()
					
					x2 = ox * self.speed
					y2 = oy * self.speed
					
					dx = x + x2
					dy = y + y2
					
					# 座標を四捨五入する丸め処理
					ddx = math.floor(dx + 0.5)
					ddy = math.floor(dy + 0.5)
					
					if ddx <= 1 or ddx >= 511:
						dx = x
					
					if ddy <= 1 or ddy >= 511:
						dy = y
					
					if self.protocol.map.get_solid(ddx, ddy, z+1):
						dx = x
						dy = y
					
					self.set_location((dx, dy, z))
					self.damage_stock += 0.3
					if self.damage_stock >= 1.0:
						self.set_hp(self.hp - 1, type = FALL_KILL)
						self.damage_stock -= 1.0
					if not self.regene:
						self.regenerate()
						self.regene = True
					callLater(0.01, self.spurt)
		
		"""
		Spurtで消費したHPを徐々に回復する
		Restore HP, consumed by Spurt
		"""
		def regenerate(self):
			# ログアウト後にループ処理が残らないよう、存在の確認
			if isinstance(self.world_object, type(None)):
				return
			if self.hp < 100 and self.hp != 0:
				self.set_hp(self.hp + 1, type = FALL_KILL)
			callLater(1, self.regenerate)
		
		def goal_successed(self, teamname):
			if teamname == 'blue':
				goal_team = self.protocol.blue_team
			elif teamname == 'green':
				goal_team = self.protocol.green_team
			else:
				goal_team = self.team.other
			old_team = self.team
			if self.team is goal_team:
				self.drop_flag()
				self.send_chat('!!OWN GOAL!!')
				self.team = goal_team.other
				fill_create_player(self, self.team)
				self.protocol.send_contained(create_player, save = True)
				self.take_flag()
			goal_team.flag.player = self
			self.capture_flag()
			if old_team is goal_team:
				self.team = old_team
				fill_create_player(self, self.team)
				self.protocol.send_contained(create_player, save = True)
			flash_color = goal_team.other.color
			self.protocol.fog_flash(flash_color)
			callLater(0.5, self.protocol.fog_flash, flash_color)
			callLater(0.9, self.protocol.fog_flash, flash_color)
			for player in goal_team.other.get_players():
				player.kill(self, MELEE_KILL)
		
		def on_flag_take(self):
			if self.protocol.mode_throwin and self.protocol.throwin_team is not self.team:
				return False
			else:
				if self.protocol.mode_throwin:
					self.send_chat("You can only shoot gun or throw nade")
					self.send_chat("!! THROW IN !!")
				flag = self.team.flag
				if flag.player is None:
					flag.set(*HIDE_POS)
					flag.update()
				else:
					return False
				self.refill()
				self.have_ball = True
				return connection.on_flag_take(self)

		def on_flag_drop(self):
			flag = self.team.other.flag
			position = self.protocol.flag_spawn_pos
			x = position[0]
			y = position[1]
			z = self.protocol.map.get_z(x, y, 60)
			flag.set(x, y, z)
			flag.update()
			flag = self.team.flag
			flag.set(x, y, z)
			flag.update()
			self.have_ball = False
			return connection.on_flag_drop(self)
		
		
		def on_block_destroy(self, x, y, z, mode):
			if self.god:
				if self.goal_making:
					if self.block1_x == None:
						self.block1_x = x
						self.block1_y = y
						self.block1_z = z
						self.send_chat('first block was selected')
					else:
						if self.block1_x > x:
							x1 = x
							x2 = self.block1_x
						else:
							x1 = self.block1_x
							x2 = x
						if self.block1_y > y:
							y1 = y
							y2 = self.block1_y
						else:
							y1 = self.block1_y
							y2 = y
						if self.block1_z > z:
							z1 = z
							z2 = self.block1_z
						else:
							z1 = self.block1_z
							z2 = z
						self.protocol.highest_id += 1
						id = self.protocol.highest_id
						teamname = self.arguments[1]
						if teamname == 'b' or teamname == 'blue':
							belong_team = 'blue'
						elif teamname == 'g' or teamname == 'green':
							belong_team = 'green'
						else:
							belong_team = 'neutral'
						goal = GoalObject(id, belong_team, x1, x2, y1, y2, z1, z2)
						self.protocol.goals[id] = goal
						self.goal_making = False
						self.send_chat('goal was created')
					return False
				else:
					return connection.on_block_destroy(self, x, y, z, mode)
			else:
				if mode == GRENADE_DESTROY:
					flag = self.team.other.flag
					if checkHolder(self, flag):
						self.protocol.flag_spawn_pos = (x, y, z)
						goal = self.protocol.is_goal(x, y, z)
						if goal:
							self.goal_successed(goal.teamname)
						elif not checkCoatInside(self, x, y):
							dx, dy = calcOutsidePosition(self, x, y)
							self.protocol.flag_spawn_pos = (dx, dy, z)
							self.protocol.mode_throwin = True
							self.protocol.throwin_team = self.team.other
							game_reset_loop(self, THROWIN_TIME)
							self.protocol.declareThrowIn(self.protocol.throwin_team)
						else:
							self.protocol.mode_throwin = False
						self.drop_flag()
						self.have_ball = False
				return False
		
		
		def on_grenade_thrown(self, grenade):
			self.have_ball = False
			self.grenades = 0
			return connection.on_grenade_thrown(self, grenade)
		
		def on_block_build_attempt(self, x, y, z):
			if self.god:
				return connection.on_block_build_attempt(self, x, y, z)
			else:
				return False

		
		def on_line_build_attempt(self, points):
			if self.god:
				return connection.on_line_build_attempt(self, points)
			else:
				return False
		
		
		def on_hit(self, hit_amount, hit_player, type, grenade):
			if type == MELEE_KILL and self.team != hit_player.team:
				if self.protocol.mode_throwin:
					message = MESSAGE_THROW_IN.format(team = self.protocol.throwin_team.name)
					self.protocol.send_chat(message, global_message = False)
					self.kill(self, MELEE_KILL)
				else:
					flag = self.team.flag
					if hit_player.have_ball:
						hit_player.drop_flag()
						hit_player.have_ball = False
						self.take_flag()
						self.have_ball = True
						flag.set(*HIDE_POS)
						flag.update()
						return connection.on_hit(self, 0, hit_player, type, grenade)
			elif type == WEAPON_KILL or type == HEADSHOT_KILL:
				if self.team == hit_player.team:
					flag = self.team.other.flag
					if self.have_ball:
						self.protocol.mode_throwin = False
						self.drop_flag()
						self.have_ball = False
						hit_player.take_flag()
						hit_player.have_ball = True
				elif self.team != hit_player.team:
					flag = hit_player.team.flag
					if self.have_ball:
						self.protocol.mode_throwin = False
						self.drop_flag()
						self.have_ball = False
						hit_player.take_flag()
						hit_player.have_ball = True
						flag.set(*HIDE_POS)
						flag.update()
			return False
		
		def on_spawn_location(self, pos):
			return self.team.spawn_pos
		
		def on_team_leave(self, team):
			flag = self.team.other.flag
			if checkHolder(self, flag):
				x, y, z = self.world_object.position.get()
				self.protocol.flag_spawn_pos = (x, y, z)
				self.drop_flag()
				self.have_ball = False
		
		def on_team_switch_attempt(self, team):
			flag = self.team.other.flag
			if checkHolder(self, flag):
				x, y, z = self.world_object.position.get()
				self.protocol.flag_spawn_pos = (x, y, z)
				self.drop_flag()
				self.have_ball = False
		
		def on_team_changed(self, team):
			if team.id != 0 and team.id != 1:
				return
			flag = team.other.flag
			if checkHolder(self, flag):
				x, y, z = self.world_object.position.get()
				self.protocol.flag_spawn_pos = (x, y, z)
				self.drop_flag()
				self.have_ball = False
			blue = 0
			green = 0
			for p in self.protocol.blue_team.get_players():
				blue += 1
			for p in self.protocol.green_team.get_players():
				green += 1
		
		def on_disconnect(self):
			if self.team != None:
				if self.team.id == 0 or self.team.id == 1:
					flag = self.team.other.flag
					if checkHolder(self, flag):
						x, y, z = self.world_object.position.get()
						self.protocol.flag_spawn_pos = (x, y, z)
						self.drop_flag()
						self.have_ball = False
			return connection.on_disconnect(self)
			
		"""
		位置座標の更新時に呼び出される処理
		Check location of the player who hold the Intel
		"""
		def on_position_update(self):
			# 敵側インテルの定義
			flag = self.team.other.flag
			
			# インテル（ボール）を所持している場合の処理
			if self.have_ball:
				
				# 位置座標の取得
				x, y, z = self.world_object.position.get()
				
				# godモード（サーバ管理者による編集権限）の時は何もせず後続処理
				if self.god:
					return connection.on_pasition_update(self)
				
				# スローインモード時以外の処理
				elif not self.protocol.mode_throwin:
					
					# 座標が場外の時の処理
					if not checkCoatInside(self, x, y):
						dx, dy = calcOutsidePosition(self, x, y)
						self.protocol.flag_spawn_pos = (dx, dy, z)
						self.drop_flag()
						self.have_ball = False
						self.kill(self, MELEE_KILL)
						self.protocol.mode_throwin = True
						self.protocol.throwin_team = self.team.other
						game_reset_loop(self, THROWIN_TIME)
						self.protocol.declareThrowIn(self.protocol.throwin_team)
				# スローインモードの時の処理
				else:
					bx, by, bz = self.protocol.flag_spawn_pos
					pos = (bx, by, z)
					self.set_location(pos)
		
		def on_walk_update(self, up, dw, le, ri):
			if self.have_ball and self.protocol.mode_throwin:
				self.send_chat("Pass the intel by shooting")
				self.send_chat("or")
				self.send_chat("Throw grenade")
				self.send_chat("You can't walk")
				self.send_chat("Now on THROW-IN")
				
				x, y, z = self.world_object.position.get()
				bx, by, bz = self.protocol.flag_spawn_pos
				pos = (bx, by, z)
				self.set_location(pos)
			return connection.on_walk_update(self, up, dw, le, ri)
		
		def on_animation_update(self,jump,crouch,sneak,sprint):
			if sneak:
				self.sneak = True
				self.spurt()
			else:
				self.sneak = False
			return connection.on_animation_update(self,jump,crouch,sneak,sprint)
		
		def on_secondary_fire_set(self, secondary):
			if secondary and self.tool == WEAPON_TOOL:
				self.scope = True
				self.spurt()
			else:
				self.scope = False
			return connection.on_secondary_fire_set(self, secondary)
		
		def on_tool_changed(self, tool):
			self.scope = False
			return connection.on_tool_changed(self, tool)
		
		def on_kill(self, killer, type, grenade):
			self.regene = False
			return connection.on_kill(self, killer, type, grenade)
	
	
	return BasketBallProtocol, BasketBallConnection