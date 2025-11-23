# import logger
import json

import aiohttp
import imgkit
import os
import sys
import jinja2  # 添加Jinja2导入
import requests
import base64
import asyncio
from datetime import datetime, timedelta
from pyppeteer import launch
import math

from ...model.EVE.sde import SdeUtils
from ..market_server import MarketManager
from ..config_server.config import config
from ..evesso_server import eveesi
from ...utils import KahunaException, get_beijing_utctime
from ...utils.path import TMP_PATH, RESOURCE_PATH
from ..log_server import logger

# 模板目录
template_path = os.path.join(RESOURCE_PATH, "templates")
# CSS目录
css_path = os.path.join(RESOURCE_PATH, "css")

def format_number(value):
    """将数字格式化为带千位分隔符的字符串"""
    try:
        # 转换为浮点数
        num = float(value)
        # 如果是整数，不显示小数部分
        if num.is_integer():
            return "{:,}".format(int(num))
        # 否则保留两位小数
        return "{:,.2f}".format(num)
    except (ValueError, TypeError):
        # 如果无法转换为数字，返回原值
        return value

# 方法2：直接添加到环境
def round_filter(value, precision=2):
    try:
        return round(float(value), precision)
    except (ValueError, TypeError):
        return value

class PictureRender():
    @classmethod
    def check_tmp_dir(cls):
        # 确保临时目录存在
        if not os.path.exists(TMP_PATH):
            os.makedirs(TMP_PATH)

    @classmethod
    async def render_price_res_pic(cls, item_id: int, price_data: list, history_data: list, order_data):
        # 准备实时价格数据
        max_buy, mid_price, min_sell, fuzz_list = price_data
        item_name = await SdeUtils.get_name_by_id(item_id)

        cls.check_tmp_dir()

        # 获取Jinja2环境
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )

        # 根据是否有模糊匹配结果选择模板
        try:
            # 下载并转换物品图片
            item_image_path = await cls.download_eve_item_image(await SdeUtils.get_id_by_name(item_name))  # 这里的ID需要根据实际物品ID修改
            item_image_base64 = cls.get_image_base64(item_image_path) if item_image_path else None
            env.filters['format_number'] = format_number
            # 假设 order_data 是你原有的订单数据字典
            buy_orders = [[k, v] for k, v in order_data['buy_order'].items()]
            buy_orders.sort(key=lambda x: x[1]['price'], reverse=True)
            sell_orders = [[k, v] for k, v in order_data['sell_order'].items()]
            sell_orders.sort(key=lambda x: x[1]['price'])
            template = env.get_template('price_template.j2')
            html_content = template.render(
                item_name=item_name,
                max_buy=f"{max_buy:,.2f}",
                mid_price=f"{mid_price:,.2f}",
                min_sell=f"{min_sell:,.2f}",
                item_image_base64=item_image_base64,
                sell_orders=sell_orders,
                buy_orders=buy_orders,
                price_history = history_data
            )
        except jinja2.exceptions.TemplateNotFound as e:
            logger.error(f"模板文件不存在: {e}")
            logger.error(f"请确保模板文件已放置在 {template_path} 目录下")
            return None

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "price_res.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=550, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_single_cost_pic(cls, single_cost_data: dict):
        """
        single_cost.j2 模板需要填充的数据字段:

        1. 物品基本信息:
           - item_name: 物品英文名称，如 "Wyvern"
           - item_name_cn: 物品中文名称，如 "飞龙级"
           - item_id: 物品ID，如 23917
           - item_icon_url: 物品图标URL (可选)，如不提供将显示默认图标

        2. 成本和利润信息:
           - cost: 物品成本，如 132432132
           - profit: 利润值，如 21321321，正值显示绿色，负值显示红色
           - profit_rate: 利润率，如 16.1，显示为百分比，正值显示绿色，负值显示红色

        3. JITA交易数据:
           - jita_sell: JITA卖出价，如 111111111
           - jita_mid: JITA中间价，如 111111111
           - jita_buy: JITA买入价，如 111111111

        4. 饼图数据:
           - cost_components: 成本组成部分的列表，每个组件为字典，包含:
             - name: 组件名称，如 "A", "B", "C", "D"
             - value: 组件值（数值或百分比），如 25
             - color: 颜色名称（对应Tailwind的颜色），如 "red", "blue", "green", "yellow"
             - rgba_bg: 背景RGBA值 (可选)，如 "255, 99, 132, 0.8"
             - rgba_border: 边框RGBA值 (可选)，如 "255, 99, 132, 1"

        注意: 所有数值类型数据会通过format_number过滤器格式化，需要在渲染前注册此过滤器。
        """

        material_dict = single_cost_data['material']
        group_detail = single_cost_data['group_detail']
        eiv_cost = single_cost_data['eiv']

        # 1.
        item_id = single_cost_data['type_id']
        item_name = await SdeUtils.get_name_by_id(item_id)
        iten_name_cn = await SdeUtils.get_cn_name_by_id(item_id)
        item_icon_url = await cls.get_eve_item_icon_base64(item_id)

        # 3.
        jita_buy, jita_mid, jita_sell, _ = single_cost_data["market_detail"]

        # 2.
        cost = single_cost_data['total_cost']
        profit = single_cost_data['profit'] = jita_sell - cost
        profit_rate = profit / cost

        # 4. 修改饼图数据处理，确保使用正确的值
        group_cost_list = [[group, data[0], data[1]] for group, data in group_detail.items()]
        group_cost_list.sort(key=lambda x: x[1], reverse=True)
        cost_components = [
            {
                'name': group_data[0],
                'value': group_data[1],  # 使用实际成本值而不是百分比
            }
            for group_data in group_cost_list
        ]
        cost_components.append(
            {
                'name': '系数',
                'value': eiv_cost[0]
            }
        )

        # 开始渲染图片
        # 获取Jinja2环境
        try:
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(template_path),
                autoescape=jinja2.select_autoescape(['html', 'xml'])
            )
            env.filters['format_number'] = format_number
            template = env.get_template('single_cost.j2')
            html_content = template.render(
                item_name=item_name,
                item_name_cn=iten_name_cn,
                item_id=item_id,
                item_icon_url=item_icon_url,
                jita_buy=jita_buy,
                jita_mid=jita_mid,
                jita_sell=jita_sell,
                cost=cost,
                profit=profit,
                profit_rate=profit_rate,
                cost_components=cost_components
            )
            with open(os.path.join(TMP_PATH, "single_cost.html"), 'w', encoding='utf-8') as f:
                f.write(html_content)
        except jinja2.exceptions.TemplateNotFound as e:
            logger.error(f"模板文件不存在: {e}")
            logger.error(f"请确保模板文件已放置在 {template_path} 目录下")
            return None

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "single_cost_res.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=550, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_sell_list(cls, sell_asset_list: list, price_type: str):
        """
            j2模板传入
            items = [
                {
                    'icon': 'base64_encoded_image',  # 物品图标的base64编码
                    'name': '物品名称',
                    'price': 1000000,  # 售价
                    'quantity': 10     # 剩余数量
                },
                # ... 更多物品
            ]
            """
        jita_mk = MarketManager.get_market_by_type('jita')
        items = []
        for asset in sell_asset_list:
            buy, sell = await jita_mk.get_type_order_rouge(asset.type_id)
            if price_type == 'mid':
                price = (buy + sell) / 2
            elif price_type == 'buy':
                price = buy
            else:
                price = sell
            if sell == 0:
                price = '价格详谈'
            data = {
                'icon': await PictureRender.get_eve_item_icon_base64(asset.type_id),
                'id': asset.type_id,
                'name': await SdeUtils.get_name_by_id(asset.type_id),
                'cn_name': await SdeUtils.get_cn_name_by_id(asset.type_id),
                'price': price,
                'quantity': asset.quantity,
                'country': (await SdeUtils.get_market_group_list(asset.type_id, zh=True))[-2],
                'ship_type': await SdeUtils.get_groupname_by_id(asset.type_id, zh=True)
            }
            items.append(data)
        items.sort(key=lambda x: x['ship_type'], reverse=True)

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_number'] = format_number
        template = env.get_template('sell_list_template.j2')
        current = datetime.now()
        if current.astimezone().utcoffset().total_seconds() == 0:  # 如果是UTC时区
            # 转换为北京时间 (UTC+8)
            current = current + timedelta(hours=8)
        html_content = template.render(
            items=items,
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png')),
            current_time=current.strftime('%Y-%m-%d %H:%M:%S') + ' UTC+8',
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "sell_list.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=1300, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_refine_result(cls, ref_res):
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_number'] = format_number
        template = env.get_template('refine_template.j2')
        current = datetime.now()
        if current.astimezone().utcoffset().total_seconds() == 0:  # 如果是UTC时区
            # 转换为北京时间 (UTC+8)
            current = current + timedelta(hours=8)
        html_content = template.render(
            data=ref_res,
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png'))
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "refine_report.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=1000, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def rebder_mk_feature(cls, mk_data: dict):
        data_list = [data for data in mk_data.values() if data['profit_rate'] < 2]
        data_list.sort(key=lambda x: x['month_profit'], reverse=True)
        feature_list = [
            data for data in data_list
            if data['cost'] * data['asset_exist'] < 1500000000
            and data['cost'] > 30000000
        ][:30]

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_number'] = format_number
        template = env.get_template('t2mk_template.j2')
        current = get_beijing_utctime(datetime.now())
        html_content = template.render(
            all_data=data_list,
            feature_list=feature_list,
            header_title='T2常规舰船市场推荐',
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png'))
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "mk_feature.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=1100, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path


    @classmethod
    async def render_buy_list(cls, lack_dict: dict, provider_data: dict):
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_number'] = format_number
        template = env.get_template('buy_list_template.j2')
        current = get_beijing_utctime(datetime.now())
        html_content = template.render(
            buy_list_data=lack_dict,
            provider_data=provider_data,
            header_title='采购清单',
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png'))
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "buy_list.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=1200, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_asset_statistic_report(cls, data):
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_number'] = format_number
        template = env.get_template('asset_statistic_template.j2')
        current = get_beijing_utctime(datetime.now())
        html_content = template.render(
            header_title='资产分析',
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png')),
            data=data
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "asset_statistic.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=1500, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_order_state(cls, data, is_buy_order=False):
        order_data = data['order_data']
        for order in order_data:
            order.update({
                'icon': await PictureRender.get_eve_item_icon_base64(order['type_id']),
                'date_remain': order['duration'] - (get_beijing_utctime(datetime.now()) - order['issued']).days,
            })
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_number'] = format_number
        template = env.get_template('order_state.j2')
        html_content = template.render(
            header_title= '收购订单状态' if is_buy_order else '出售订单状态',
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png')),
            order_data=order_data,
            is_buy_order=is_buy_order
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "order_state.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=900, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_month_order_statistic(cls, data):
        for type_data in data['sell_type_data'].values():
            type_data.update({'icon': await PictureRender.get_eve_item_icon_base64(type_data['type_id'])})

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_number'] = format_number
        template = env.get_template('month_order_statistic.j2')
        current = get_beijing_utctime(datetime.now())
        html_content = template.render(
            header_title='月KPI统计',
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png')),
            data=data
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "month_kpi.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=1600, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_moon_material_state(cls, data: dict, market_index_history: list):
        for _, R_data in data.items():
            for tid, t_data in R_data.items():
                t_data.update({'icon': await PictureRender.get_eve_item_icon_base64(tid)})

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_number'] = format_number
        template = env.get_template('moon_material_state_template.j2')
        current = get_beijing_utctime(datetime.now())
        html_content = template.render(
            header_title='元素市场',
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png')),
            data=data,
            rarity_list=list(data.keys()),
            market_index_history=market_index_history
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "moon_material_state.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=1600, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_coop_pay_report(cls, data: dict):
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        env.filters['format_currency'] = format_number
        env.filters['round'] = round_filter
        template = env.get_template('coop_pay_template.j2')
        current = get_beijing_utctime(datetime.now())
        html_content = template.render(
            header_title='合作报酬',
            header_image=PictureRender.get_image_base64(os.path.join(RESOURCE_PATH, 'img', 'sell_list_header.png')),
            data=data
        )

        # 生成输出路径
        output_path = os.path.abspath(os.path.join((TMP_PATH), "coop_pay_template.jpg"))

        # 增加等待时间到5秒，确保图表有足够时间渲染
        pic_path = await cls.render_pic(output_path, html_content, width=800, height=720, wait_time=120)

        if not pic_path:
            raise KahunaException("pic_path not exist.")
        return pic_path

    @classmethod
    async def render_pic(cls, output_path: str, html_content: str, width: int = 800, height: int = 800, wait_time: int = 5):
        # 将HTML内容保存到临时文件
        html_file_path = os.path.join(TMP_PATH, "temp_render.html")
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        launch_a = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',  # 禁用GPU加速
        ]

        if config['APP']['PIC_RENDER_PROXY'] != '':
            proxy_arg = [config['APP']['PIC_RENDER_PROXY']]
        else:
            proxy_arg = []

        # 检查是否为 Linux 系统
        if sys.platform.startswith('linux'):
        # 启动浏览器，添加必要的参数以确保在Linux环境下正常运行
            browser = await launch(
                headless=True,
                args=launch_a + proxy_arg
            )

        else:
            browser = await launch(
                executablePath=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                headless=True,
                args=proxy_arg
            )

        page = await browser.newPage()
        await page.setViewport({'width': width, 'height': height})

        try:
            # 设置页面内容
            await page.setContent(html_content)

            # 等待字体加载完成
            await page.waitForFunction('document.fonts.ready', {'timeout': wait_time * 1000})

            # 检查是否有Chart.js图表，如果有则等待图表渲染完成
            has_chart = await page.evaluate('typeof Chart !== "undefined" && document.getElementById("costChart") !== null')
            if has_chart:
                # 禁用Chart.js动画以加速渲染
                await page.evaluate('''
                    if (typeof Chart !== "undefined") {
                        Chart.defaults.animation = false;
                        // 添加一个全局标志，表示图表渲染完成
                        window.chartRendered = false;
                        const originalDraw = Chart.prototype.draw;
                        Chart.prototype.draw = function() {
                            originalDraw.apply(this, arguments);
                            window.chartRendered = true;
                        };
                    }
                ''')

                # 等待图表渲染完成或超时
                try:
                    await page.waitForFunction('window.chartRendered === true', {'timeout': wait_time * 1000})
                except Exception as e:
                    logger.warning(f"等待图表渲染超时: {e}，使用备用等待时间")
                    await asyncio.sleep(wait_time)  # 备用等待机制
            else:
                # 如果没有图表，等待DOM内容加载完成
                await page.waitForFunction('document.readyState === "complete"')
                # 额外等待一小段时间确保CSS渲染完成
                await asyncio.sleep(1)

            # 截图
            await page.screenshot({'path': output_path, 'fullPage': True})
        except Exception as e:
            logger.error(f"渲染过程发生错误: {e}")
            # 记录更详细的错误信息
            logger.error(f"详细错误: {str(e)}")
            logger.error(f"错误类型: {type(e).__name__}")
        finally:
            try:
                if 'browser' in locals() and browser:
                    await browser.close()
            except Exception as close_error:
                logger.error(f"关闭浏览器时发生错误: {close_error}")

        return output_path


    @classmethod
    async def get_eve_item_icon_base64(cls, type_id: int):
        item_image_path = await cls.download_eve_item_image(type_id)  # 这里的ID需要根据实际物品ID修改
        item_image_base64 = cls.get_image_base64(item_image_path) if item_image_path else None

        return item_image_base64

    @classmethod
    async def get_character_portrait_base64(cls, character_id: int):
        portrait_image_path = await cls.download_character_protrait(character_id)
        portrait_image_base64 = cls.get_image_base64(portrait_image_path)

        return portrait_image_base64

    @classmethod
    async def download_eve_item_image(cls, type_id: int, size: int = 64) -> str:
        """
        下载EVE物品图片
        :param type_id: 物品ID
        :param size: 图片尺寸，可选值：64, 1024
        :return: 图片本地路径
        """
        # 创建图片存储目录
        image_path = os.path.join(RESOURCE_PATH, "img")
        if not os.path.exists(image_path):
            os.makedirs(image_path)

        # 构建图片URL和本地保存路径
        local_path = os.path.join(image_path, f"item_{type_id}_{size}.png")

        # 如果图片已存在，直接返回路径
        if os.path.exists(local_path):
            return local_path

        # 尝试从主URL下载（现在使用原来的备用URL作为主URL）
        try:
            # 主URL（原备用URL）
            url = f"https://imageserver.eveonline.com/Type/{type_id}_{size}.png"
            logger.info(f"尝试从主URL下载: {url}")

            # 下载图片，禁用SSL验证
            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        content = await response.read()
                        # 保存图片
                        with open(local_path, 'wb') as f:
                            f.write(content)

                        logger.info(f"成功下载物品图片: {type_id}")
                        return local_path
                    else:
                        raise Exception(f"请求状态码: {response.status}")
        except Exception as e:
            logger.error(f"从主URL下载EVE物品图片失败: {e}")

            # 尝试备用URL（原主URL）
            try:
                # 备用URL
                backup_url = f"https://images.evetech.net/types/{type_id}/icon?size={size}"
                logger.info(f"尝试从备用URL下载: {backup_url}")

                async with aiohttp.ClientSession() as session:
                    async with session.get(backup_url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.read()
                            with open(local_path, 'wb') as f:
                                f.write(content)

                            logger.info(f"从备用URL成功下载物品图片: {type_id}")
                            return local_path
                        else:
                            raise Exception(f"备用URL请求状态码: {response.status}")

            except Exception as backup_e:
                logger.error(f"从备用URL下载EVE物品图片也失败: {backup_e}")

            # 如果两个URL都失败，返回默认图片路径
            default_image = os.path.join(RESOURCE_PATH, "img", "default_item.png")

            # 如果默认图片不存在，创建一个简单的默认图片
            if not os.path.exists(default_image):
                try:
                    # 创建一个简单的1x1像素透明PNG
                    with open(default_image, 'wb') as f:
                        f.write(base64.b64decode(
                            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="))
                except Exception:
                    logger.error("无法创建默认图片")
                    return None

            return default_image

    @classmethod
    def get_image_base64(cls, image_path: str) -> str:
        """将图片转换为base64编码"""
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            logger.error(f"图片转base64失败: {e}")
            return None

    @classmethod
    async def download_character_protrait(cls, character_id: int):
        # 创建图片存储目录
        image_path = os.path.join(RESOURCE_PATH, "img")
        if not os.path.exists(image_path):
            os.makedirs(image_path)

        # 构建图片URL和本地保存路径
        local_path = os.path.join(image_path, f"portrait_{character_id}.png")

        # 如果图片已存在，直接返回路径
        if os.path.exists(local_path):
            return local_path

        image_data = await eveesi.characters_character_portrait(character_id)
        px64_url = image_data['px64x64']

        # 下载图片，禁用SSL验证
        async with aiohttp.ClientSession() as session:
            async with session.get(px64_url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    content = await response.read()
                    # 保存图片
                    with open(local_path, 'wb') as f:
                        f.write(content)

                    logger.info(f"成功下载角色头像: {character_id}")
                    return local_path
                else:
                    raise Exception(f"请求状态码: {response.status}")

        return local_path
