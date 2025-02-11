from astrbot.api.all import *
import random
import json
import os

# 定义扑克游戏状态类
class PokerGame:
    def __init__(self, buyin: int, small_blind: int, big_blind: int, bet_amount: int, max_players: int):
        self.buyin = buyin                  # 加入游戏时支付的买入金额
        self.small_blind = small_blind        # 小盲注金额
        self.big_blind = big_blind            # 大盲注金额
        self.bet_amount = bet_amount          # 后续每轮固定跟注金额
        self.max_players = max_players        # 最大玩家数
        # 每个玩家记录结构：{"id": str, "name": str, "cards": list, "private_unified": str, "round_bet": int, "active": bool}
        self.players = []                     
        self.deck = self.create_deck()        # 洗好的牌堆
        self.community_cards = []             # 公共牌
        self.phase = "waiting"                # 游戏阶段：waiting, preflop, flop, turn, river, showdown
        self.pot = 0                        # 当前彩池
        self.current_bet = 0                # 当前轮要求的投注额度

    def create_deck(self):
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck

    def deal_card(self):
        if not self.deck:
            self.deck = self.create_deck()
        return self.deck.pop()

@register("texas_holdem_poker", "w33d", "Texas Hold'em Poker Bot插件", "1.0.1", "repo url")
class TexasHoldemPoker(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        # 按照群聊（或私聊）ID隔离的游戏状态
        self.games = {}  
        # 按照群组ID存储代币余额，结构为 {group_id: {user_id: token}}
        self.tokens_file = os.path.join(os.path.dirname(__file__), "tokens.json")
        self.tokens = self.load_tokens()

    def load_tokens(self):
        try:
            if os.path.exists(self.tokens_file):
                with open(self.tokens_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print("加载tokens失败:", e)
        return {}

    def save_tokens(self):
        try:
            with open(self.tokens_file, "w", encoding="utf-8") as f:
                json.dump(self.tokens, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("保存tokens失败:", e)

    def get_group_id(self, event: AstrMessageEvent) -> str:
        group_id = event.message_obj.group_id
        # 如果群组ID为空，则认为是私聊，使用 "private_{发送者ID}" 作为标识
        if not group_id:
            group_id = f"private_{event.get_sender_id()}"
        return group_id

    @command_group("poker")
    def poker():
        '''德州扑克指令组'''
        pass

    @poker.command("start")
    async def start_game(self, event: AstrMessageEvent):
        '''开始一局新的德州扑克游戏'''
        group_id = self.get_group_id(event)
        if group_id in self.games:
            yield event.plain_result("本群已存在正在进行的游戏，请结束当前游戏后再开始新游戏。")
            return
        buyin = self.config.get("buyin", 100)
        small_blind = self.config.get("small_blind", 10)
        big_blind = self.config.get("big_blind", 20)
        bet_amount = self.config.get("bet_amount", 20)
        max_players = self.config.get("max_players", 9)
        self.games[group_id] = PokerGame(buyin, small_blind, big_blind, bet_amount, max_players)
        yield event.plain_result(
            f"新德州扑克游戏开始！买入: {buyin}, 小盲注: {small_blind}, 大盲注: {big_blind}, 每轮跟注金额: {bet_amount}, 最大玩家: {max_players}。\n请发送 `/poker join` 加入游戏。"
        )

    @poker.command("join")
    async def join_game(self, event: AstrMessageEvent):
        '''加入当前德州扑克游戏'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏，请先使用 `/poker start` 开始游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()
        for player in game.players:
            if player["id"] == sender_id:
                yield event.plain_result("你已经加入了本局游戏。")
                return
        # 如果在群聊中加入，则构造用于私信的统一会话ID（格式为 "private_{sender_id}"），否则直接使用 event.unified_msg_origin
        if event.message_obj.group_id:
            private_unified = f"private_{sender_id}"
        else:
            private_unified = event.unified_msg_origin

        # 初始化该群的代币数据
        if group_id not in self.tokens:
            self.tokens[group_id] = {}
        if sender_id not in self.tokens[group_id]:
            initial_token = self.config.get("initial_token", 1000)
            self.tokens[group_id][sender_id] = initial_token
        buyin = game.buyin
        if self.tokens[group_id][sender_id] < buyin:
            yield event.plain_result(f"余额不足，买入需要 {buyin} 代币。你当前余额: {self.tokens[group_id][sender_id]}")
            return
        self.tokens[group_id][sender_id] -= buyin
        self.save_tokens()
        game.pot += buyin
        game.players.append({
            "id": sender_id,
            "name": sender_name,
            "cards": [],
            "private_unified": private_unified,
            "round_bet": 0,
            "active": True
        })
        yield event.plain_result(
            f"{sender_name} 加入游戏，扣除买入 {buyin} 代币。当前彩池: {game.pot} 代币。你当前余额: {self.tokens[group_id][sender_id]}"
        )

    @poker.command("deal")
    async def deal_hole_cards(self, event: AstrMessageEvent):
        '''发牌：给每个玩家发两张手牌（通过私信发送），并分配盲注'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        if len(game.players) < 2:
            yield event.plain_result("至少需要2名玩家才能开始游戏。")
            return
        if game.phase != "waiting":
            yield event.plain_result("游戏已经开始发牌了。")
            return
        # 为每个玩家发两张手牌，并通过私信发送（使用存储的 private_unified）
        for player in game.players:
            card1 = game.deal_card()
            card2 = game.deal_card()
            player["cards"] = [card1, card2]
            chain = MessageChain().message(f"你的手牌: {card1} {card2}")
            await self.context.send_message(player["private_unified"], chain)
        # 分配盲注：第一个玩家为小盲，第二个为大盲
        small_blind_player = game.players[0]
        sb_amount = game.small_blind
        group_tokens = self.tokens[group_id]
        available = group_tokens.get(small_blind_player["id"], 0)
        sb = min(available, sb_amount)
        group_tokens[small_blind_player["id"]] = available - sb
        small_blind_player["round_bet"] += sb
        game.pot += sb

        big_blind_player = game.players[1]
        available = group_tokens.get(big_blind_player["id"], 0)
        bb_amount = game.big_blind
        bb = min(available, bb_amount)
        group_tokens[big_blind_player["id"]] = available - bb
        big_blind_player["round_bet"] += bb
        game.pot += bb

        self.save_tokens()
        game.current_bet = game.big_blind
        game.phase = "preflop"
        yield event.plain_result(
            f"手牌已发出，各玩家请查看私信。\n盲注分配：{small_blind_player['name']} 小盲 {sb}，{big_blind_player['name']} 大盲 {bb}。\n当前预注金额为 {game.current_bet} 代币。请使用 `/poker call` 跟注，或 `/poker next` 进入下一阶段。"
        )

    @poker.command("call")
    async def call_bet(self, event: AstrMessageEvent):
        '''跟注：支付差额使当前投注达到预注金额'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        player = None
        for p in game.players:
            if p["id"] == sender_id and p["active"]:
                player = p
                break
        if not player:
            yield event.plain_result("你不在当前游戏中或已弃牌。")
            return
        if player["round_bet"] >= game.current_bet:
            yield event.plain_result("你已经跟注了。")
            return
        required = game.current_bet - player["round_bet"]
        group_tokens = self.tokens[group_id]
        if group_tokens.get(sender_id, 0) < required:
            yield event.plain_result(f"余额不足，需跟注 {required} 代币。你当前余额: {group_tokens.get(sender_id, 0)}")
            return
        group_tokens[sender_id] -= required
        player["round_bet"] += required
        game.pot += required
        self.save_tokens()
        yield event.plain_result(f"你已跟注，支付 {required} 代币。当前彩池: {game.pot} 代币。")

    @poker.command("fold")
    async def fold(self, event: AstrMessageEvent):
        '''弃牌：放弃本局游戏'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        found = False
        for p in game.players:
            if p["id"] == sender_id and p["active"]:
                p["active"] = False
                found = True
                yield event.plain_result(f"{p['name']} 已弃牌。")
                break
        if not found:
            yield event.plain_result("你不在当前游戏中或已弃牌。")
            return
        # 检查是否只剩下唯一活跃玩家
        active_players = [p for p in game.players if p["active"]]
        if len(active_players) == 1:
            winner = active_players[0]
            group_tokens = self.tokens[group_id]
            group_tokens[winner["id"]] += game.pot
            self.save_tokens()
            yield event.plain_result(f"只有 {winner['name']} 一人未弃牌，赢得彩池 {game.pot} 代币！")
            del self.games[group_id]

    @poker.command("next")
    async def next_round(self, event: AstrMessageEvent):
        '''进入下一阶段：检查所有活跃玩家是否跟注，然后进入下一轮或摊牌'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        not_called = [p["name"] for p in game.players if p["active"] and p["round_bet"] < game.current_bet]
        if not_called:
            yield event.plain_result("以下玩家还未跟注: " + ", ".join(not_called))
            return

        if game.phase == "preflop":
            game.deal_card()  # 烧牌
            flop_cards = [game.deal_card() for _ in range(3)]
            game.community_cards.extend(flop_cards)
            game.phase = "flop"
            for p in game.players:
                if p["active"]:
                    p["round_bet"] = 0
            game.current_bet = game.bet_amount
            yield event.plain_result(
                f"翻牌: {' '.join(flop_cards)}。\n当前轮下注金额为 {game.current_bet} 代币。请使用 `/poker call` 跟注，或 `/poker next` 进入下一阶段。"
            )
        elif game.phase == "flop":
            game.deal_card()  # 烧牌
            turn_card = game.deal_card()
            game.community_cards.append(turn_card)
            game.phase = "turn"
            for p in game.players:
                if p["active"]:
                    p["round_bet"] = 0
            game.current_bet = game.bet_amount
            yield event.plain_result(
                f"转牌: {turn_card}。\n当前轮下注金额为 {game.current_bet} 代币。请使用 `/poker call` 跟注，或 `/poker next` 进入下一阶段。"
            )
        elif game.phase == "turn":
            game.deal_card()  # 烧牌
            river_card = game.deal_card()
            game.community_cards.append(river_card)
            game.phase = "river"
            for p in game.players:
                if p["active"]:
                    p["round_bet"] = 0
            game.current_bet = game.bet_amount
            yield event.plain_result(
                f"河牌: {river_card}。\n当前轮下注金额为 {game.current_bet} 代币。请使用 `/poker call` 跟注，或 `/poker next` 进入摊牌阶段。"
            )
        elif game.phase == "river":
            result = "摊牌：\n"
            for p in game.players:
                if p["active"]:
                    result += f"{p['name']} 的手牌: {' '.join(p['cards'])}\n"
            result += f"公共牌: {' '.join(game.community_cards)}\n彩池: {game.pot} 代币。"
            yield event.plain_result(result)
            del self.games[group_id]
        else:
            yield event.plain_result("游戏阶段错误。")

    @poker.command("status")
    async def game_status(self, event: AstrMessageEvent):
        '''显示当前游戏状态'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        result = f"游戏状态: {game.phase}\n彩池: {game.pot} 代币\n玩家列表：\n"
        for p in game.players:
            status = "活跃" if p["active"] else "弃牌"
            result += f"- {p['name']}：本轮投注 {p['round_bet']} 代币，状态: {status}\n"
        if game.community_cards:
            result += f"公共牌: {' '.join(game.community_cards)}\n"
        yield event.plain_result(result)

    @poker.command("tokens")
    async def my_tokens(self, event: AstrMessageEvent):
        '''查看你的代币余额'''
        group_id = self.get_group_id(event)
        if group_id not in self.tokens:
            balance = self.config.get("initial_token", 1000)
        else:
            balance = self.tokens[group_id].get(event.get_sender_id(), self.config.get("initial_token", 1000))
        yield event.plain_result(f"你的代币余额: {balance} 代币")

    @poker.command("reset")
    async def reset_game(self, event: AstrMessageEvent):
        '''重置当前群聊的游戏状态'''
        group_id = self.get_group_id(event)
        if group_id in self.games:
            del self.games[group_id]
            yield event.plain_result("当前游戏已重置。")
        else:
            yield event.plain_result("当前群聊没有进行中的游戏。")
