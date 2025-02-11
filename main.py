from astrbot.api.all import *
import random

@register("texas_holdem", "PokerMaster", "德州扑克插件", "1.0.0")
class TexasHoldemBot(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {
            "buy_in": 1000,
            "small_blind": 10,
            "big_blind": 20,
            "max_players": 6
        }
        self.games = {}  # 存储每个群的牌局信息

    @command("poker_start")
    async def start_game(self, event: AstrMessageEvent, buy_in: int = None, small_blind: int = None, big_blind: int = None, max_players: int = None):
        """创建新的德州扑克牌局"""
        group_id = event.group_id
        if group_id in self.games:
            yield event.plain_result("已有牌局进行中，请先结束！")
            return

        self.games[group_id] = {
            "players": [],
            "deck": self.shuffle_deck(),
            "community_cards": [],
            "pot": 0,
            "small_blind": small_blind or self.config["small_blind"],
            "big_blind": big_blind or self.config["big_blind"],
            "buy_in": buy_in or self.config["buy_in"],
            "max_players": max_players or self.config["max_players"],
            "turn": 0
        }

        yield event.plain_result(f"德州扑克牌局已创建！💰 买入: {self.games[group_id]['buy_in']} 💵 小盲: {self.games[group_id]['small_blind']} 大盲: {self.games[group_id]['big_blind']}")

    @command("poker_join")
    async def join_game(self, event: AstrMessageEvent):
        """加入牌局"""
        group_id = event.group_id
        player_id = event.get_sender_id()
        
        if group_id not in self.games:
            yield event.plain_result("没有进行中的牌局，请先创建游戏！")
            return

        game = self.games[group_id]
        if len(game["players"]) >= game["max_players"]:
            yield event.plain_result("牌局人数已满！")
            return

        if any(p["id"] == player_id for p in game["players"]):
            yield event.plain_result("你已经加入牌局！")
            return

        game["players"].append({"id": player_id, "chips": game["buy_in"], "hand": []})
        yield event.plain_result(f"{event.get_sender_name()} 已加入牌局！")

    @command("poker_deal")
    async def deal_cards(self, event: AstrMessageEvent):
        """发放手牌"""
        group_id = event.group_id
        if group_id not in self.games:
            yield event.plain_result("没有正在进行的牌局，请先创建游戏！")
            return

        game = self.games[group_id]
        if not game["players"]:
            yield event.plain_result("没有玩家加入游戏，无法发牌！")
            return

        for player in game["players"]:
            player["hand"] = [game["deck"].pop(), game["deck"].pop()]
            await self.context.send_message(player["id"], MessageChain().message(f"你的手牌: {player['hand'][0]} {player['hand'][1]}"))

        yield event.plain_result("所有玩家的手牌已私信发出！")

    @command("poker_flop")
    async def flop(self, event: AstrMessageEvent):
        """翻牌 (前三张公共牌)"""
        group_id = event.group_id
        if group_id not in self.games:
            yield event.plain_result("请先创建游戏！")
            return

        game = self.games[group_id]
        if len(game["community_cards"]) > 0:
            yield event.plain_result("翻牌已发出！")
            return

        game["community_cards"] = [game["deck"].pop(), game["deck"].pop(), game["deck"].pop()]
        yield event.plain_result(f"公共牌: {game['community_cards'][0]} {game['community_cards'][1]} {game['community_cards'][2]}")

    @command("poker_turn")
    async def turn(self, event: AstrMessageEvent):
        """转牌 (第四张公共牌)"""
        group_id = event.group_id
        if group_id not in self.games or len(self.games[group_id]["community_cards"]) != 3:
            yield event.plain_result("请先翻牌！")
            return

        card = self.games[group_id]["deck"].pop()
        self.games[group_id]["community_cards"].append(card)
        yield event.plain_result(f"转牌: {card}")

    @command("poker_river")
    async def river(self, event: AstrMessageEvent):
        """河牌 (第五张公共牌)"""
        group_id = event.group_id
        if group_id not in self.games or len(self.games[group_id]["community_cards"]) != 4:
            yield event.plain_result("请先发转牌！")
            return

        card = self.games[group_id]["deck"].pop()
        self.games[group_id]["community_cards"].append(card)
        yield event.plain_result(f"河牌: {card}")

    @command("poker_end")
    async def end_game(self, event: AstrMessageEvent):
        """结束游戏并清理"""
        group_id = event.group_id
        if group_id not in self.games:
            yield event.plain_result("没有进行中的牌局！")
            return

        del self.games[group_id]
        yield event.plain_result("牌局已结束！")

    def shuffle_deck(self):
        """创建并洗牌一副扑克牌"""
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        deck = [f"{suit}{rank}" for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck
