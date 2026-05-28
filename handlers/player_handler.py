# handlers/player_handler.py
import time
import random
from datetime import datetime
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..core import CultivationManager, PillManager
from ..models import Player
from ..models_extended import UserStatus
from ..config_manager import ConfigManager
from .utils import player_required

CMD_START_XIUXIAN = "我要修仙"
CMD_PLAYER_INFO = "我的信息"
CMD_START_CULTIVATION = "闭关"
CMD_END_CULTIVATION = "出关"
CMD_CHECK_IN = "签到"
REBIRTH_COOLDOWN = 7 * 24 * 3600

__all__ = ["PlayerHandler"]

class PlayerHandler:
    """玩家基础信息处理器 - 支持灵修/体修选择"""

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.cultivation_manager = CultivationManager(config, config_manager)
        self.pill_manager = PillManager(self.db, self.config_manager)

    async def handle_start_xiuxian(self, event: AstrMessageEvent, cultivation_type: str = ""):
        """处理创建角色

        Args:
            cultivation_type: 修炼类型，"灵修"或"体修"，为空则显示选择提示
        """
        user_id = event.get_sender_id()

        # 检查是否已创建角色
        if await self.db.get_player_by_id(user_id):
            yield event.plain_result("道友，你已踏入仙途，无需重复此举。")
            return

        # 如果没有提供职业选择，显示选择提示
        if not cultivation_type or cultivation_type.strip() == "":
            help_msg = (
                "🌟 欢迎踏入修仙之路！\n"
                "━━━━━━━━━━━━━━━\n"
                "请选择你的修炼方式：\n\n"
                "【灵修】以灵气为主，法术攻击\n"
                "• 寿命：100\n"
                "• 灵气：100-1000\n"
                "• 法伤：5-100\n"
                "• 物伤：5\n"
                "• 法防：0\n"
                "• 物防：5\n"
                "• 精神力：100-500\n\n"
                "【体修】以气血为主，肉身强横\n"
                "• 寿命：50-100\n"
                "• 气血：100-500\n"
                "• 法伤：0\n"
                "• 物伤：100-500\n"
                "• 法防：50-200\n"
                "• 物防：100-500\n"
                "• 精神力：100-500\n"
                "━━━━━━━━━━━━━━━\n"
                "⚠️ 修仙风险警告 ⚠️\n"
                "• 突破失败有概率走火入魔身死道消\n"
                "• 生命值归零也会导致死亡\n"
                "• 死亡后所有数据清除，需重新入仙途\n"
                "━━━━━━━━━━━━━━━\n"
                f"💡 使用方法：\n"
                f"  {CMD_START_XIUXIAN} 灵修\n"
                f"  {CMD_START_XIUXIAN} 体修"
            )
            yield event.plain_result(help_msg)
            return

        # 验证职业类型
        cultivation_type = cultivation_type.strip()
        if cultivation_type not in ["灵修", "体修"]:
            yield event.plain_result(f"职业选择错误！请选择「灵修」或「体修」。")
            return

        # 生成新玩家
        new_player = self.cultivation_manager.generate_new_player_stats(user_id, cultivation_type)
        await self.db.create_player(new_player)

        # 获取灵根描述
        root_name = new_player.spiritual_root.replace("灵根", "")
        root_description = self.cultivation_manager._get_root_description(root_name)

        reply_msg = (
            f"🎉 恭喜道友 {event.get_sender_name()} 踏上仙途！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"修炼方式：【{new_player.cultivation_type}】\n"
            f"灵根：【{new_player.spiritual_root}】\n"
            f"评价：{root_description}\n"
            f"启动资金：{new_player.gold} 灵石\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚠️ 修仙有风险，突破需谨慎！\n"
            f"突破失败或生命值归零会导致\n"
            f"身死道消，所有数据清除！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 发送「{CMD_PLAYER_INFO}」查看状态"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_player_info(self, player: Player, event: AstrMessageEvent):
        """处理查看玩家信息 - 展示新属性"""
        display_name = event.get_sender_name()
        required_exp = player.get_required_exp(self.config_manager)

        # 更新丹药效果并计算最终属性倍率
        await self.pill_manager.update_temporary_effects(player)
        pill_multipliers = self.pill_manager.calculate_pill_attribute_effects(player)

        # 获取装备加成后的属性
        from ..core import EquipmentManager
        equipment_manager = EquipmentManager(self.db, self.config_manager)
        equipped_items = equipment_manager.get_equipped_items(
            player,
            self.config_manager.items_data,
            self.config_manager.weapons_data
        )
        total_attrs = player.get_total_attributes(equipped_items, pill_multipliers)

        # 图片生成暂时禁用（缺少资源文件会导致效果很差）
        # 直接使用优化后的文本格式显示

        # 文本模式 (完整信息显示)
        
        # 获取战力（综合攻防）
        combat_power = (
            int(total_attrs['physical_damage']) + int(total_attrs['magic_damage']) +
            int(total_attrs['physical_defense']) + int(total_attrs['magic_defense']) +
            int(total_attrs['mental_power']) // 10
        )
        
        # 获取宗门信息
        sect_name = "无宗门"
        position_name = "散修"
        if player.sect_id and player.sect_id != 0:
            sect = await self.db.ext.get_sect_by_id(player.sect_id)
            if sect:
                sect_name = sect.sect_name
                if sect.sect_owner == player.user_id:
                    position_name = "宗主"
                elif player.sect_position == 1:
                    position_name = "长老"
                elif player.sect_position == 2:
                    position_name = "亲传弟子"
                elif player.sect_position == 3:
                    position_name = "内门弟子"
                else:
                    position_name = "外门弟子"
        
        # 获取装备信息
        weapon_name = player.weapon if player.weapon else "无"
        armor_name = player.armor if player.armor else "无"
        technique_name = player.main_technique if player.main_technique else "无"
        
        # 获取突破状态
        breakthrough_rate = f"+{player.level_up_rate}%" if player.level_up_rate > 0 else "0%"
        
        # 构建信息显示
        dao_hao = player.user_name if player.user_name else display_name
        
        reply_msg = (
            f"📋 道友 {dao_hao} 的信息\n"
            f"━━━━━━━━━━━━━━━\n"
            f"\n"
            f"【基本信息】\n"
            f"  道号：{dao_hao}\n"
            f"  境界：{player.get_level(self.config_manager)}\n"
            f"  修为：{int(player.experience):,}/{int(required_exp):,}\n"
            f"  灵石：{player.gold:,}\n"
            f"  战力：{combat_power:,}\n"
            f"  灵根：{player.spiritual_root}\n"
            f"  突破加成：{breakthrough_rate}\n"
            f"\n"
            f"【修炼属性】\n"
            f"  修炼方式：{player.cultivation_type}\n"
            f"  状态：{player.state}\n"
            f"  寿命：{player.lifespan}\n"
            f"  精神力：{total_attrs['mental_power']}\n"
        )
        
        # 根据修炼类型添加不同属性
        if player.cultivation_type == "体修":
            reply_msg += (
                f"  气血：{player.blood_qi}/{total_attrs.get('max_blood_qi', 0)}\n"
                f"  物伤：{total_attrs['physical_damage']}\n"
                f"  法伤：{total_attrs['magic_damage']}\n"
                f"  物防：{total_attrs['physical_defense']}\n"
                f"  法防：{total_attrs['magic_defense']}\n"
            )
        else:
            reply_msg += (
                f"  灵气：{player.spiritual_qi}/{total_attrs.get('max_spiritual_qi', 0)}\n"
                f"  法伤：{total_attrs['magic_damage']}\n"
                f"  物伤：{total_attrs['physical_damage']}\n"
                f"  法防：{total_attrs['magic_defense']}\n"
                f"  物防：{total_attrs['physical_defense']}\n"
            )
        
        reply_msg += (
            f"\n"
            f"【装备信息】\n"
            f"  主修功法：{technique_name}\n"
            f"  法器：{weapon_name}\n"
            f"  防具：{armor_name}\n"
            f"\n"
            f"【宗门信息】\n"
            f"  所在宗门：{sect_name}\n"
            f"  宗门职位：{position_name}\n"
        )
        
        # 获取贷款信息
        loan = await self.db.ext.get_active_loan(player.user_id)
        if loan:
            now = int(time.time())
            remaining_seconds = loan["due_at"] - now
            remaining_days = remaining_seconds // 86400
            remaining_hours = (remaining_seconds % 86400) // 3600
            
            days_borrowed = max(1, (now - loan["borrowed_at"]) // 86400)
            interest = int(loan["principal"] * loan["interest_rate"] * days_borrowed)
            total_due = loan["principal"] + interest
            
            loan_type_name = "突破贷款" if loan["loan_type"] == "breakthrough" else "普通贷款"
            
            if remaining_seconds <= 0:
                time_str = "⚠️ 已逾期！"
            elif remaining_days <= 0:
                time_str = f"🔴 {remaining_hours}小时"
            elif remaining_days <= 1:
                time_str = f"🟠 {remaining_days}天{remaining_hours}小时"
            else:
                time_str = f"🟡 {remaining_days}天"
            
            reply_msg += (
                f"\n"
                f"【贷款信息】💰\n"
                f"  类型：{loan_type_name}\n"
                f"  应还：{total_due:,} 灵石\n"
                f"  剩余：{time_str}\n"
                f"  💀 逾期将被追杀致死！\n"
            )
        
        reply_msg += "━━━━━━━━━━━━━━━"
        
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_start_cultivation(self, player: Player, event: AstrMessageEvent):
        """处理闭关指令"""
        # 检查是否已经在闭关
        if player.state == "修炼中":
            yield event.plain_result("道友已在闭关中，请勿重复进入。")
            return
        
        # 检查是否在其他活动中（历练、秘境探索等）
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 道友当前正{current_status}，无法闭关修炼！")
            return

        # 记录闭关开始时间
        player.state = "修炼中"
        player.cultivation_start_time = int(time.time())
        await self.db.update_player(player)
        await self.db.ext.set_user_busy(player.user_id, UserStatus.CULTIVATING, 0)

        yield event.plain_result(
            "🧘 道友已进入闭关状态\n"
            "━━━━━━━━━━━━━━━\n"
            "闭关期间，你将与世隔绝，潜心修炼。\n"
            f"💡 发送「{CMD_END_CULTIVATION}」结束闭关\n"
            "⏱️ 每分钟将获得修为，受灵根资质影响。"
        )

    @player_required
    async def handle_end_cultivation(self, player: Player, event: AstrMessageEvent):
        """处理出关指令"""
        # 检查是否在闭关中
        if player.state != "修炼中":
            yield event.plain_result("道友当前并未闭关，无需出关。")
            return

        # 检查是否有闭关开始时间
        if player.cultivation_start_time == 0:
            yield event.plain_result("数据异常：未记录闭关开始时间。")
            return

        # 计算闭关时长（分钟）
        end_time = int(time.time())
        duration_seconds = end_time - player.cultivation_start_time
        duration_minutes = duration_seconds // 60

        if duration_minutes < 1:
            yield event.plain_result("道友闭关时间不足1分钟，未获得修为。请继续闭关修炼。")
            return

        # 闭关时长上限根据境界调整（基础24小时，每提升一个大境界增加6小时）
        # level_index: 0-8练气, 9-17筑基, 18-26金丹, 27-35元婴, 36-44化神, 45-53炼虚, 54-62合体, 63-71大乘, 72+渡劫
        base_minutes = 1440  # 24小时
        realm_bonus = (player.level_index // 9) * 360  # 每个大境界增加6小时
        MAX_CULTIVATION_MINUTES = base_minutes + realm_bonus
        effective_minutes = min(duration_minutes, MAX_CULTIVATION_MINUTES)
        exceeded_time = duration_minutes > MAX_CULTIVATION_MINUTES

        # 获取主修心法的修为加成
        technique_bonus = 0.0
        if player.main_technique:
            from ..core import EquipmentManager
            equipment_manager = EquipmentManager(self.db, self.config_manager)
            equipped_items = equipment_manager.get_equipped_items(
                player,
                self.config_manager.items_data,
                self.config_manager.weapons_data
            )
            # 找到主修心法
            for item in equipped_items:
                if item.item_type == "main_technique":
                    technique_bonus = item.exp_multiplier
                    break

        # 分段计算修为收益（考虑丹药有效期）
        # 在更新丹药效果前先获取当前活跃效果
        original_effects = player.get_active_pill_effects()
        cultivation_start = player.cultivation_start_time
        
        # 收集所有时间节点：闭关开始、丹药过期时间、闭关结束
        time_points = {cultivation_start, end_time}
        for effect in original_effects:
            expiry_time = effect.get("expiry_time", 0)
            if expiry_time > 0:
                time_points.add(expiry_time)
        
        # 过滤出在闭关时间段内的时间点
        valid_points = [t for t in time_points if cultivation_start <= t <= end_time]
        valid_points.sort()
        
        total_exp = 0
        
        # 分段计算每段时间的修为收益
        for i in range(len(valid_points) - 1):
            segment_start = valid_points[i]
            segment_end = valid_points[i + 1]
            segment_seconds = segment_end - segment_start
            # 使用浮点数精确计算分钟数，避免边界丢失
            segment_minutes = segment_seconds / 60.0
            
            if segment_minutes < 1/60:  # 小于1秒不计算
                continue
            
            # 计算该时间段内有效的丹药效果
            current_time_for_segment = segment_start + segment_seconds // 2  # 取时间段中点
            active_effects_for_segment = []
            for effect in original_effects:
                expiry_time = effect.get("expiry_time", 0)
                if expiry_time <= 0 or current_time_for_segment < expiry_time:
                    active_effects_for_segment.append(effect)
            
            # 计算该时间段的丹药倍率
            segment_multipliers = {
                "physical_damage": 1.0,
                "magic_damage": 1.0,
                "physical_defense": 1.0,
                "magic_defense": 1.0,
                "cultivation_speed": 1.0,
            }
            
            for effect in active_effects_for_segment:
                if "physical_damage_multiplier" in effect:
                    segment_multipliers["physical_damage"] += effect["physical_damage_multiplier"]
                if "magic_damage_multiplier" in effect:
                    segment_multipliers["magic_damage"] += effect["magic_damage_multiplier"]
                if "physical_defense_multiplier" in effect:
                    segment_multipliers["physical_defense"] += effect["physical_defense_multiplier"]
                if "magic_defense_multiplier" in effect:
                    segment_multipliers["magic_defense"] += effect["magic_defense_multiplier"]
                if "cultivation_multiplier" in effect:
                    segment_multipliers["cultivation_speed"] += effect["cultivation_multiplier"]
            
            # 确保倍率不为负
            for key in segment_multipliers:
                segment_multipliers[key] = max(0.0, segment_multipliers[key])
            
            # 计算该段时间的修为
            segment_exp = self.cultivation_manager.calculate_cultivation_exp(
                player,
                segment_minutes,
                technique_bonus,
                segment_multipliers
            )
            total_exp += segment_exp

        # 更新丹药效果（处理过期效果和周期性效果）
        await self.pill_manager.update_temporary_effects(player)
        
        # 计算获得的修为
        gained_exp = total_exp

        # 更新玩家数据
        player.experience += gained_exp
        player.state = "空闲"
        player.cultivation_start_time = 0
        await self.db.update_player(player)
        await self.db.ext.set_user_free(player.user_id)

        # 计算闭关时长显示
        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        time_str = ""
        if hours > 0:
            time_str += f"{hours}小时"
        if minutes > 0:
            time_str += f"{minutes}分钟"

        # 超时提示
        exceed_msg = ""
        if exceeded_time:
            effective_hours = MAX_CULTIVATION_MINUTES // 60
            exceed_msg = f"\n⚠️ 闭关超过{effective_hours}小时，仅计算前{effective_hours}小时修为"

        reply_msg = (
            "🌟 道友出关成功！\n"
            "━━━━━━━━━━━━━━━\n"
            f"⏱️ 闭关时长：{time_str}\n"
            f"📈 获得修为：{gained_exp:,}{exceed_msg}\n"
            f"💫 当前修为：{player.experience:,}\n"
            "━━━━━━━━━━━━━━━\n"
            "道友已回归红尘，可继续修行。"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_check_in(self, player: Player, event: AstrMessageEvent):
        """处理签到指令"""
        # 获取今天的日期（格式：YYYY-MM-DD）
        today = datetime.now().strftime("%Y-%m-%d")

        # 检查是否已经签到过
        if player.last_check_in_date == today:
            yield event.plain_result(
                "📅 道友今日已经签到过了\n"
                "请明日再来。"
            )
            return

        # 获取签到奖励范围配置
        check_in_gold_min = self.config["VALUES"].get("CHECK_IN_GOLD_MIN", 50)
        check_in_gold_max = self.config["VALUES"].get("CHECK_IN_GOLD_MAX", 500)

        # 确保最小值不大于最大值
        if check_in_gold_min > check_in_gold_max:
            check_in_gold_min, check_in_gold_max = check_in_gold_max, check_in_gold_min

        # 生成随机奖励
        check_in_gold = random.randint(check_in_gold_min, check_in_gold_max)

        # 更新玩家数据
        player.gold += check_in_gold
        player.last_check_in_date = today
        await self.db.update_player(player)

        reply_msg = (
            "✅ 签到成功！\n"
            "━━━━━━━━━━━━━━━\n"
            f"💰 获得灵石：{check_in_gold}\n"
            f"💎 当前灵石：{player.gold}\n"
            "━━━━━━━━━━━━━━━\n"
            "明日再来，莫要忘记哦~"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_rebirth(self, player: Player, event: AstrMessageEvent, confirm_text: str = ""):
        """弃道重修（7天冷却）"""
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            status_name = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 你当前正在「{status_name}」，无法弃道重修。")
            return

        if player.state != "空闲":
            yield event.plain_result("❌ 只有处于空闲状态时才能弃道重修。请先结束闭关/历练等活动。")
            return

        loan = await self.db.ext.get_active_loan(player.user_id)
        if loan:
            yield event.plain_result("❌ 你仍有未结清的灵石贷款，无法重修。请先还款。")
            return

        key = f"rebirth_last_{player.user_id}"
        last_ts = await self.db.ext.get_system_config(key)
        now = int(time.time())
        if last_ts:
            diff = now - int(last_ts)
            if diff < REBIRTH_COOLDOWN:
                remaining = REBIRTH_COOLDOWN - diff
                days = remaining // 86400
                hours = (remaining % 86400) // 3600
                minutes = (remaining % 3600) // 60
                yield event.plain_result(
                    "⌛ 弃道重修冷却中\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"距离下次重修还需：{days}天{hours}小时{minutes}分钟"
                )
                return

        if confirm_text.strip() != "确认":
            yield event.plain_result(
                "⚠️ 弃道重修将删除当前角色的所有数据，并无法撤回！\n"
                "限制：每7天只能重修一次，且必须在空闲状态、无贷款时使用。\n"
                "━━━━━━━━━━━━━━━\n"
                "若你已做好准备，请发送：\n"
                "弃道重修 确认"
            )
            return

        await self.db.delete_player_cascade(player.user_id)
        await self.db.ext.set_system_config(key, str(now))

        yield event.plain_result(
            "💀 你选择了弃道重修，旧生一切化为尘埃。\n"
            "━━━━━━━━━━━━━━━\n"
            "可立即使用「我要修仙」重新踏上仙途。\n"
            "（7天内不可再次重修）"
        )
