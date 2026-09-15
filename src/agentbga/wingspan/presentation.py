"""Original concise player-facing descriptions of structured powers."""

def power_summary(power):
    k = power['kind']
    n = power.get('count', 1)
    foods = '/'.join(power.get('foods', ['any food']))
    nest = power.get('nest', 'any')
    reward = power.get('reward', '')
    text = {
        'none': 'No power.', 'food': f'Gain {n} {foods} from supply.',
        'feeder': f'Choose 1 {foods} from feeder.' + (' Keep it or cache it here.' if power.get('cache') else ''),
        'eggs': f'Lay {n} egg on ' + ('this bird.' if power.get('self') else f'{nest} nest bird' + (' other than this bird.' if power.get('other') else '.')),
        'draw': f'Draw {n} bird card(s); choose tray or deck.',
        'tuck': 'Tuck one hand card here.' + ({'draw': ' Then draw a card.', 'egg': ' Then optionally lay an egg here.',
                   'food': f' Then gain {foods} from supply.'}.get(reward, '')),
        'egg_trade': 'Spend one egg' + (' from another bird' if power.get('other') else '') + f' to gain {n} ' + ('food of your choice from supply.' if reward == 'food' else 'bird cards.'),
        'hunt_dice': f'Roll dice outside feeder; a {power.get("food", "")} face caches one matching food here.',
        'hunt_card': f'Reveal top bird: wingspan below {power.get("limit", 0)} cm tucks it here; otherwise discard it.',
        'draft': 'Draw player count + 1 cards. Each player chooses one clockwise, starting with you; keep the last.',
        'food_tuck': f'Spend one {power.get("food", "")} to tuck two deck cards here.',
        'all_feeder': 'Choose a starting player; everyone chooses one feeder food in clockwise order.',
        'nest_eggs': f'Lay one egg on each of your {nest} nest birds; star nests qualify.',
        'bonus': 'Draw two new bonus cards and keep one.',
        'feeder_all': f'Gain all {foods} currently in feeder; normal reroll option applies.',
        'all_food': f'Everyone gains one {power.get("food", "")} from supply.',
        'all_draw': 'Everyone draws one card from the deck.',
        'move': 'If rightmost in its row, move this bird to another habitat with space.',
        'draw_discard': f'Draw up to {n} cards, then discard one hand card at turn end if you drew.',
        'cache': f'Cache one {power.get("food", "")} from supply here.',
        'extra_bird': f'Play another bird in {power.get("habitat", "")} habitat, paying food and eggs.',
        'repeat': 'Repeat ' + ('a predator' if power.get('predator') else 'another brown') + ' power in this habitat. It acts on its original bird.',
        'trade': 'Exchange one food for a different food type from supply.',
        'fewest': f'Player(s) with fewest birds in {power.get("habitat", "")} may ' + ('draw one card.' if reward == 'draw' else 'gain one feeder food.'),
        'all_eggs': f'Everyone may lay an egg on one {nest} nest bird; you may use a second distinct qualifying bird.',
    }[k]
    if power.get('trigger'):
        trigger = {'lay_eggs': 'takes the lay eggs action', 'play_wetland': 'plays a wetland bird',
                   'play_forest': 'plays a forest bird', 'play_grassland': 'plays a grassland bird',
                   'predator': 'succeeds at hunting', 'gain_rodent': 'gains rodent during the gain food action'}[power['trigger']]
        text = f'Once between your turns, when another player {trigger}: '+text
    return text


def power_summary_cn(power):
    food_names = {'invertebrate':'无脊椎动物','seed':'种子','fish':'鱼','fruit':'果实','rodent':'啮齿动物'}
    nests = {'bowl':'碗巢','cavity':'洞巢','ground':'地巢','platform':'平台巢','any':'任意巢'}
    habitats = {'forest':'森林','grassland':'草原','wetland':'湿地','same':'此鸟所在的'}
    k, n = power['kind'], power.get('count', 1)
    food = food_names.get(power.get('food'), '')
    foods = '或'.join(food_names[f] for f in power.get('foods', [])) or '任意食物'
    nest = nests[power.get('nest', 'any')]
    reward = power.get('reward', '')
    text = {
        'none': '无特殊能力。', 'food': f'从供应区获得 {n} 个{foods}。',
        'feeder': f'从鸟食器选择 1 个{foods}；须有相应骰面。'+('可保留或贮藏在此鸟上。' if power.get('cache') else ''),
        'eggs': f'在'+('此鸟' if power.get('self') else ('另一只' if power.get('other') else '一只')+nest+'鸟')+f'上放置 {n} 枚蛋。',
        'draw': f'抽取 {n} 张鸟牌，可选公开牌或牌堆。',
        'tuck': '将一张手牌压在此鸟下。'+{'draw':'然后抽一张鸟牌。','egg':'然后可在此鸟上放一枚蛋。','food':f'然后从供应区获得一个{foods}。'}.get(reward,''),
        'egg_trade': '弃掉'+('其他鸟上的' if power.get('other') else '')+'一枚蛋，'+(f'从供应区获得 {n} 个任意食物。' if reward=='food' else f'抽取 {n} 张鸟牌。'),
        'hunt_dice': f'重掷鸟食器外的骰子；若出现{food}，在此鸟上贮藏一个{food}。',
        'hunt_card': f'翻开牌堆顶牌：翼展小于 {power.get("limit",0)} cm 则压在此鸟下，否则弃置。',
        'draft': '抽取玩家人数加一张牌；从你开始顺时针每人选一张，你保留最后一张。',
        'food_tuck': f'弃掉一个{food}，将牌堆顶两张牌压在此鸟下。',
        'all_feeder': '选择起始玩家，所有玩家顺时针各从鸟食器拿一个食物。',
        'nest_eggs': f'在你每只{nest}鸟上放一枚蛋；万能巢也符合条件。',
        'bonus': '抽取两张新奖励卡，保留一张。',
        'feeder_all': f'获得鸟食器内所有{foods}；可按一般规则重掷。',
        'all_food': f'所有玩家各从供应区获得一个{food}。',
        'all_draw': '所有玩家各从牌堆抽一张鸟牌。',
        'move': '若此鸟位于所在栖息地最右侧，可迁徙到另一个有空位的栖息地。',
        'draw_discard': f'可抽取 {n} 张鸟牌；若抽过牌，在本回合结束时弃一张手牌。',
        'cache': f'从供应区拿一个{food}，贮藏在此鸟上。',
        'extra_bird': f'可在{habitats.get(power.get("habitat"),"")}栖息地额外打出一只鸟，正常支付食物和鸟蛋。',
        'repeat': '重复此栖息地中'+('一个捕食' if power.get('predator') else '另一只鸟的棕色')+'能力，效果仍作用于原来的鸟。',
        'trade': '用一个食物交换供应区中另一种食物。',
        'fewest': f'{habitats.get(power.get("habitat"),"")}鸟数最少的玩家（含并列）'+('各抽一张鸟牌。' if reward=='draw' else '各从鸟食器拿一个食物。'),
        'all_eggs': f'所有玩家可在一只{nest}鸟上放一枚蛋；你可再选另一只符合条件的鸟放一枚蛋。',
    }[k]
    if power.get('trigger'):
        event = {'lay_eggs':'执行产蛋行动','play_wetland':'打出湿地鸟','play_forest':'打出森林鸟',
                 'play_grassland':'打出草原鸟','predator':'捕食成功','gain_rodent':'在获得食物行动中拿到啮齿动物'}[power['trigger']]
        text = f'你的两次回合之间最多一次：其他玩家{event}时，'+text
    return text
