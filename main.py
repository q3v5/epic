import requests
import os
from datetime import datetime, timedelta
import html

# 1. 获取 GitHub Secrets（PushPlus 配置）
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

def get_epic_free_games():
    url = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US"
    try:
        res = requests.get(url).json()
        games = res['data']['Catalog']['searchStore']['elements']
        
        free_games = []
        for game in games:
            # 基础过滤
            promotions = game.get('promotions')
            if not promotions: continue
            if not promotions.get('promotionalOffers'): continue
            
            offers = promotions['promotionalOffers']
            if not offers: continue

            is_free = False
            end_date_str = "未知"
            is_new_game = False # 标记是否为新上架的游戏

            for offer_group in offers:
                for offer in offer_group['promotionalOffers']:
                    if offer['discountSetting']['discountPercentage'] == 0:
                        is_free = True
                        
                        # 处理截止时间
                        raw_end_date = offer.get('endDate')
                        raw_start_date = offer.get('startDate') # 获取开始时间
                        
                        if raw_end_date:
                            try:
                                dt_end = datetime.strptime(raw_end_date.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                                end_date_str = dt_end.strftime("%Y-%m-%d %H:%M") + " (UTC)"
                            except:
                                end_date_str = raw_end_date
                        
                        # 判断是否为新上架游戏（28小时内）
                        if raw_start_date:
                            try:
                                dt_start = datetime.strptime(raw_start_date.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                                now = datetime.utcnow()
                                time_diff = now - dt_start
                                
                                if time_diff < timedelta(hours=28):
                                    is_new_game = True
                                else:
                                    print(f"跳过旧游戏: {game.get('title')} (已上架 {time_diff})")
                            except Exception as e:
                                print(f"时间解析错误: {e}")
                                is_new_game = True # 解析失败默认推送
                        else:
                            is_new_game = True # 无开始时间默认推送
                        
                        break
            
            # 仅收集免费且新上架的游戏
            if is_free and is_new_game:
                title = game.get('title')
                description = game.get('description', '暂无描述')
                slug = game.get('productSlug') or game.get('urlSlug')
                link = f"https://store.epicgames.com/p/{slug}" if slug else "https://store.epicgames.com/free-games"
                
                image_url = ""
                for img in game.get('keyImages', []):
                    if img.get('type') == 'Thumbnail':
                        image_url = img.get('url')
                        break
                    elif img.get('type') == 'OfferImageWide':
                        image_url = img.get('url')

                free_games.append({
                    "title": title,
                    "description": description,
                    "link": link,
                    "image": image_url,
                    "end_date": end_date_str
                })
                
        return free_games
        
    except Exception as e:
        print(f"获取 Epic 数据出错: {e}")
        return []

def send_pushplus_message(content, title="Epic免费游戏提醒", template="html", channel="wechat"):
    """
    按照PushPlus官方GET请求规范发送消息
    :param content: 消息内容（必填）
    :param title: 消息标题（非必填，默认值：Epic免费游戏提醒）
    :param template: 消息模板（非必填，默认值：html）
    :param channel: 发送渠道（非必填，默认值：wechat）
    :return: 推送结果（布尔值）
    """
    # 校验必填参数
    if not PUSHPLUS_TOKEN:
        print("❌ 错误：未设置 PUSHPLUS_TOKEN（必填参数）")
        return False
    if not content:
        print("❌ 错误：content消息内容为必填参数")
        return False
    
    # 构建GET请求参数（严格匹配官方文档）
    params = {
        "token": PUSHPLUS_TOKEN,       # 必填：用户令牌
        "title": title,                # 非必填：消息标题
        "content": content,            # 必填：消息内容
        "template": template,          # 非必填：模板类型，默认html
        "channel": channel             # 非必填：发送渠道，默认wechat
        # 其他可选参数（如webhook/callbackUrl/timestamp等，可根据需要添加）
    }
    
    # 官方提示：太长的消息内容用POST请求，这里增加长度判断提示
    if len(content) > 2000:
        print("⚠️ 提示：content内容长度超过2000字符，建议改用POST请求方式")
    
    try:
        # 发送GET请求（符合官方文档的GET请求方式）
        response = requests.get(
            url="https://www.pushplus.plus/send",
            params=params,
            timeout=10  # 增加超时保护
        )
        result = response.json()
        
        # 解析返回结果
        if result.get("code") == 200:
            print("✅ PushPlus推送成功")
            return True
        else:
            print(f"❌ PushPlus推送失败：{result.get('msg', '未知错误')}")
            return False
    except requests.exceptions.Timeout:
        print("❌ 推送请求超时")
        return False
    except Exception as e:
        print(f"❌ 推送请求异常：{str(e)}")
        return False

if __name__ == "__main__":
    print("⏳ 开始检查 Epic 免费游戏 (每日去重版)...")
    games = get_epic_free_games()
    
    if games:
        print(f"🎉 发现 {len(games)} 个新上架的免费游戏")
        for g in games:
            safe_title = html.escape(g['title'])
            safe_desc = html.escape(g['description'])
            
            # 构建符合PushPlus的HTML消息内容
            msg_content = (
                f"<div style='margin: 10px 0;'>"
                f"<h3>🔥 Epic 喜加一提醒 🔥</h3>"
                f"<p><strong>🎮 游戏名称：</strong>{safe_title}</p>"
                f"<p><strong>⏰ 截止时间：</strong>{g['end_date']}</p>"
                f"<p><strong>📝 游戏描述：</strong>{safe_desc}</p>"
                f"<p><strong>🔗 领取链接：</strong><a href='{g['link']}'>点击领取游戏</a></p>"
                f"</div>"
                f"<div style='margin: 10px 0;'><img src='{g['image']}' alt='游戏封面' style='max-width: 100%; border-radius: 4px;'></div>"
            )
            # 调用推送函数（严格传参）
            send_pushplus_message(content=msg_content)
    else:
        print("🤷‍♂️ 今天没有新上架的免费游戏 (可能是旧游戏已通知过)")
