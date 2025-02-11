from astrbot.api.all import *
import random
import json
import os

# 用于维护德州扑克游戏状态的类
class PokerGame:
    def __init__(self, buyin: int, small_blind: int, big_blind: int, bet_amount: int, max_players: int):
        self.buyin = buyin                # 加入游戏时需支付的买入金额
        self.small_blind = small_blind      # 小盲注金额
        self.big_blind = big_blind          # 大盲注金额
        self.bet_amount = bet_amount        # 每轮固定跟注金额（除预注外，后续每轮的投注额度）
        self.max_players = max_players      # 游戏允许的最大玩家数
        self.players = []                   # 每个玩家记录：{"id": str, "name": str, "cards": list, "unified": str, "round_bet": int}
        self.deck = self.create_deck()      # 洗好的牌堆
        self.community_cards = []           # 公共牌
        self.phase = "waiting"              # 游戏阶段：waiting, preflop, flop, turn, river, showdown
        self.pot = 0                        # 当前彩池
        self.current_bet = 0                # 当前轮要求的投注额

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

@register("texas_holdem_poker", "Your Name", "Texas Hold'em Poker Bot插件", "1.0.0", "repo url")
class TexasHoldemPoker(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.game = None
        # tokens.json 用于持久化存储每个玩家的代币余额
        self.tokens_file = os.path.join(os.path.dirname(__file__), "tokens.json")
        self.tokens = self.load_tokens()

    def load_tokens(self):
        if os.path.exists(self.tokens_file):
            try:
                with open(self.tokens_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print("加载tokens失败:", e)
                return {}
        else:
            return {}

    def save_tokens(self):
        try:
            with open(self.tokens_file, "w", encoding="utf-8") as f:
                json.dump(self.tokens, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("保存tokens失败:", e)

    # 指令组：poker
    @command_group("poker")
    def poker():
        '''德州扑克指令组'''
        pass

    @poker.command("start")
    async def start_game(self, event: AstrMessageEvent):
        '''开始一局新的德州扑克游戏'''
        if self.game is not None:
            yield event.plain_result("游戏已经在进行中，请结束当前游戏后再开始新游戏。")
            return
        # 从配置中读取参数（如果配置中没有，则使用默认值）
        buyin = self.config.get("buyin", 100)
        small_blind = self.config.get("small_blind", 10)
        big_blind = self.config.get("big_blind", 20)
        bet_amount = self.config.get("bet_amount", 20)
        max_players = self.config.get("max_players", 9)
        self.game = PokerGame(buyin, small_blind, big_blind, bet_amount, max_players)
        yield event.plain_result(
            f"新德州扑克游戏开始！买入: {buyin}, 小盲注: {small_blind}, 大盲注: {big_blind}, 每轮跟注金额: {bet_amount}, 最大玩家: {max_players}。\n请发送 `/poker join` 加入游戏。"
        )

    @poker.command("join")
    async def join_game(self, event: AstrMessageEvent):
        '''加入当前德州扑克游戏'''
        if self.game is None:
            yield event.plain_result("当前没有正在进行的游戏，请先使用 `/poker start` 开始游戏。")
            return
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()
        # 检查是否已加入
        for player in self.game.players:
            if player["id"] == sender_id:
                yield event.plain_result("你已经加入了游戏。")
                return
        buyin = self.game.buyin
        # 如果该玩家没有代币记录，则初始化为配置中的初始代币数量
        if sender_id not in self.tokens:
            initial_token = self.config.get("initial_token", 1000)
            self.tokens[sender_id] = initial_token
        # 检查余额是否足够支付买入金额
        if self.tokens[sender_id] < buyin:
            yield event.plain_result(f"余额不足，买入需要 {buyin} 代币。你当前余额: {self.tokens[sender_id]}")
            return
        # 扣除买入金额
        self.tokens[sender_id] -= buyin
        self.save_tokens()
        self.game.pot += buyin
        # 添加玩家记录，初始时本轮投注为0
        self.game.players.append({
            "id": sender_id,
            "name": sender_name,
            "cards": [],
            "unified": event.unified_msg_origin,
            "round_bet": 0
        })
        yield event.plain_result(
            f"{sender_name} 加入游戏，扣除买入 {buyin} 代币。当前彩池: {self.game.pot} 代币。你当前余额: {self.tokens[sender_id]}"
        )

    @poker.command("deal")
    async def deal_hole_cards(self, event: AstrMessageEvent):
        '''发牌：给每个玩家发两张手牌（通过私信发送）并分配盲注'''
        if self.game is None:
            yield event.plain_result("当前没有正在进行的游戏。")
            return
        if len(self.game.players) < 2:
            yield event.plain_result("至少需要2名玩家才能开始游戏。")
            return
        if self.game.phase != "waiting":
            yield event.plain_result("游戏已经开始发牌了。")
            return
        # 给每个玩家发两张手牌，并通过私信发送
        for player in self.game.players:
            card1 = self.game.deal_card()
            card2 = self.game.deal_card()
            player["cards"] = [card1, card2]
            chain = MessageChain().message(f"你的手牌: {card1} {card2}")
            await self.context.send_message(player["unified"], chain)
        # 分配盲注：第一个玩家为小盲，第二个为大盲
        small_blind_player = self.game.players[0]
        sb_amount = self.game.small_blind
        available = self.tokens.get(small_blind_player["id"], 0)
        sb = min(available, sb_amount)
        self.tokens[small_blind_player["id"]] = available - sb
        small_blind_player["round_bet"] += sb
        self.game.pot += sb

        big_blind_player = self.game.players[1]
        available = self.tokens.get(big_blind_player["id"], 0)
        bb_amount = self.game.big_blind
        bb = min(available, bb_amount)
        self.tokens[big_blind_player["id"]] = available - bb
        big_blind_player["round_bet"] += bb
        self.game.pot += bb

        self.save_tokens()
        # 设置当前轮投注额为大盲注金额
        self.game.current_bet = self.game.big_blind
        self.game.phase = "preflop"
        yield event.plain_result(
            f"手牌已发出，各玩家请查看私信。\n盲注分配：{small_blind_player['name']} 小盲 {sb}，{big_blind_player['name']} 大盲 {bb}。\n当前预注金额为 {self.game.current_bet}。请使用 `/poker call` 进行跟注，或 `/poker next` 进入下一阶段。"
        )

    @poker.command("call")
    async def call_bet(self, event: AstrMessageEvent):
        '''跟注：支付差额使得当前投注达到预注金额'''
        if self.game is None:
            yield event.plain_result("当前没有正在进行的游戏。")
            return
        sender_id = event.get_sender_id()
        # 查找该玩家是否在游戏中
        player = None
        for p in self.game.players:
            if p["id"] == sender_id:
                player = p
                break
        if player is None:
            yield event.plain_result("你不在当前游戏中。")
            return
        if player["round_bet"] >= self.game.current_bet:
            yield event.plain_result("你已经跟注了。")
            return
        required = self.game.current_bet - player["round_bet"]
        if self.tokens.get(sender_id, 0) < required:
            yield event.plain_result(f"余额不足，需跟注 {required} 代币。你当前余额: {self.tokens.get(sender_id, 0)}")
            return
        self.tokens[sender_id] -= required
        player["round_bet"] += required
        self.game.pot += required
        self.save_tokens()
        yield event.plain_result(f"你已跟注，支付 {required} 代币。当前彩池: {self.game.pot}")

    @poker.command("next")
    async def next_round(self, event: AstrMessageEvent):
        '''进入下一阶段：检查是否所有玩家都跟注，然后进入翻牌/转牌/河牌或摊牌'''
        if self.game is None:
            yield event.plain_result("当前没有正在进行的游戏。")
            return
        # 检查是否所有玩家的本轮投注达到当前预注金额
        not_called = [p["name"] for p in self.game.players if p["round_bet"] < self.game.current_bet]
        if not_called:
            yield event.plain_result("以下玩家还未跟注: " + ", ".join(not_called))
            return
        if self.game.phase == "preflop":
            # 发翻牌：烧一张牌，再发3张公共牌
            self.game.deal_card()  # 烧牌
            flop_cards = [self.game.deal_card() for _ in range(3)]
            self.game.community_cards.extend(flop_cards)
            self.game.phase = "flop"
            # 重置每个玩家的本轮投注，并设置新一轮投注额
            for p in self.game.players:
                p["round_bet"] = 0
            self.game.current_bet = self.game.bet_amount
            yield event.plain_result(
                f"翻牌: {' '.join(flop_cards)}。\n当前轮下注金额为 {self.game.current_bet}。请使用 `/poker call` 跟注，或 `/poker next` 进入下一阶段。"
            )
        elif self.game.phase == "flop":
            # 发转牌：烧牌，再发1张公共牌
            self.game.deal_card()  # 烧牌
            turn_card = self.game.deal_card()
            self.game.community_cards.append(turn_card)
            self.game.phase = "turn"
            for p in self.game.players:
                p["round_bet"] = 0
            self.game.current_bet = self.game.bet_amount
            yield event.plain_result(
                f"转牌: {turn_card}。\n当前轮下注金额为 {self.game.current_bet}。请使用 `/poker call` 跟注，或 `/poker next` 进入下一阶段。"
            )
        elif self.game.phase == "turn":
            # 发河牌：烧牌，再发1张公共牌
            self.game.deal_card()  # 烧牌
            river_card = self.game.deal_card()
            self.game.community_cards.append(river_card)
            self.game.phase = "river"
            for p in self.game.players:
                p["round_bet"] = 0
            self.game.current_bet = self.game.bet_amount
            yield event.plain_result(
                f"河牌: {river_card}。\n当前轮下注金额为 {self.game.current_bet}。请使用 `/poker call` 跟注，或 `/poker next` 进入摊牌阶段。"
            )
        elif self.game.phase == "river":
            # 摊牌：展示所有玩家的手牌和公共牌
            result = "摊牌：\n"
            for p in self.game.players:
                result += f"{p['name']} 的手牌: {' '.join(p['cards'])}\n"
            result += f"公共牌: {' '.join(self.game.community_cards)}\n"
            result += f"彩池: {self.game.pot} 代币。"
            yield event.plain_result(result)
            # 本局结束，重置游戏状态
            self.game = None
        else:
            yield event.plain_result("游戏阶段错误。")

    @poker.command("status")
    async def game_status(self, event: AstrMessageEvent):
        '''显示当前游戏状态'''
        if self.game is None:
            yield event.plain_result("当前没有正在进行的游戏。")
            return
        result = f"游戏状态: {self.game.phase}\n彩池: {self.game.pot} 代币\n"
        result += "玩家列表:\n"
        for p in self.game.players:
            result += f"- {p['name']}：本轮投注 {p['round_bet']} 代币\n"
        if self.game.community_cards:
            result += f"公共牌: {' '.join(self.game.community_cards)}\n"
        yield event.plain_result(result)

    @poker.command("tokens")
    async def my_tokens(self, event: AstrMessageEvent):
        '''查看你的代币余额'''
        sender_id = event.get_sender_id()
        balance = self.tokens.get(sender_id, self.config.get("initial_token", 1000))
        yield event.plain_result(f"你的代币余额: {balance} 代币")
