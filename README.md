
<div align="center">

# 🌟 Kahuna Bot 🌟

![Logo](https://github.com/user-attachments/assets/40c09a45-f898-4167-9315-20df6a1dc59a)

[![开发状态](https://img.shields.io/badge/状态-开发中-yellow)](https://github.com/AraragiEro/astrbot_plugin_kahunabot)
[![EVE Online](https://img.shields.io/badge/游戏-EVE%20Online-blue)](https://www.eveonline.com/)
[![AstrBot](https://img.shields.io/badge/框架-AstrBot-green)](https://github.com/AstrBotDevs/AstrBot.git)

_笨笨的kahuna不停的计算自己离买牛角包还有多远_

_一座新的**X**山拔地而起！_

🥰 _爱来自 凛冬联盟群 紫竹梅重工_

![sty](https://github.com/user-attachments/assets/f37a6a06-b925-4836-8561-282720f06506)

</div>

## 📝 项目简介

本插件是基于AstrBot框架的EVE Online游戏辅助机器人，为玩家提供市场价格查询、成本计算、工业规划等功能。

> ⚠️ 本插件处于早期开发阶段，还有好多好多的bug~
> 
> 欢迎提issue~

## 📋 目录

- [🌟 Kahuna Bot 🌟](#-kahuna-bot-)
  - [📝 项目简介](#-项目简介)
  - [📋 目录](#-目录)
  - [⭐ 功能展示](#-功能展示)
    - [吉他和联盟市场价格查询](#吉他和联盟市场价格查询)
    - [成本查询](#成本查询)
    - [工业规划与报表输出](#工业规划与报表输出)
    - [化矿分析](#化矿分析)
    - [可自定义数据来源的采购清单](#可自定义数据来源的采购清单)
    - [利润分析](#利润分析)
    - [挂单分析](#挂单分析)
    - [资产统计](#资产统计)
  - [😇 如何部署？](#-如何部署)
    - [部署AstrBot](#部署astrbot)
    - [下载插件](#下载插件)
    - [配置插件](#配置插件)
      - [安装依赖](#安装依赖)
      - [准备SDE数据库](#准备sde数据库)
      - [飞书API获取](#飞书api获取)
      - [修改配置文件](#修改配置文件)
  - [关于工业规划如何使用的一份粗略的说明，先凑合用](#关于工业规划如何使用的一份粗略的说明先凑合用)
  - [🌟 支持一下](#-支持一下)

---

## ⭐ 功能展示

### 吉他和联盟市场价格查询
![吉他和联盟市场价格查询](https://github.com/user-attachments/assets/fc70e5ea-51af-41b2-b947-93ccfa6aa908)

### 成本查询
![成本查询](https://github.com/user-attachments/assets/924da9e1-335d-422f-b2b3-2fbb441b6915)

### 工业规划与报表输出
![工业规划](https://github.com/user-attachments/assets/f23b7873-dbb3-48df-9ee9-4d07ed4dba21)

![报表输出1](https://github.com/user-attachments/assets/9d2f4b57-04a4-4f31-909e-fbb72e86e4fb)

![报表输出2](https://github.com/user-attachments/assets/235c724e-f465-4966-98b8-0dc4cf7acc50)

### 化矿分析
<img src="https://github.com/user-attachments/assets/8a1f865f-ec7a-416d-9640-fd87f3e46b55" height=1200>

### 可自定义数据来源的采购清单
<img src="https://github.com/user-attachments/assets/25b891e5-8bb8-4d77-b55a-f6e1c6e2d389" height=800>

### 利润分析
<img src="https://github.com/user-attachments/assets/514b9bbc-20b6-4e13-a7a5-dfb8e5db43ef" height=1200>

### 挂单分析
<img src="https://github.com/user-attachments/assets/1e05f586-66b5-4495-a431-e6b8770131c5" height=800>

### 资产统计
<img src="https://github.com/user-attachments/assets/aa6a15b5-6902-4e38-9ec7-bfb09566de89" height=800>


👉 报表内容丰富，包括任务分解，材料采购，物流清单，工作任务等，一站式解放工业制造的脑力消耗，🫡公司级别提供智能计算服务。

---

## 😇 如何部署？

### 部署AstrBot

本项目是AstrBot框架面向QQ的机器人插件，你需要先部署基于AstrBot的QQ机器人。

👉 前往 [AstrBot官方仓库](https://github.com/AstrBotDevs/AstrBot.git) 获取详细部署指南。

### 下载插件

插件暂时没有上架插件商场，需要手动部署。

首先前往plugin目录：
```
AstrBot/
├── [其他文件]/
├── data/
│   ├── [其他文件]/
│   ├── plugins/              # 插件目录
```

将项目clone到plugin文件夹下：
```bash
git clone https://github.com/AraragiEro/astrbot_plugin_kahunabot.git
```

kahunabot的目录结构如下：

```
kahunabot/
├── src/                    # 源代码目录
│   ├── event/              # 事件处理模块
│   ├── permission_checker/ # 权限检查模块
│   ├── resource/           # 资源文件目录
│   │   ├── css/           # 样式文件
│   │   ├── img/           # 图片资源
│   │   └── templates/     # 模板文件
│   ├── rule_checker/      # 规则检查模块[废弃]
│   ├── service/           # 服务模块
│   │   ├── asset_server/  # 资产服务
│   │   ├── character_server/  # 角色管理服务
│   │   ├── config_server/  # 配置管理服务
│   │   ├── database_server/  # 数据库服务
│   │   ├── eveeso_server/  # eve api管理服务
│   │   ├── feishu_server/  # 飞书api管理服务
│   │   ├── google_server/  # 谷歌表格api管理服务
│   │   ├── industry_server/  # 工业计算服务
│   │   ├── log_server/  # 日志服务
│   │   ├── market_server/ # 市场服务
│   │   ├── sde_service/   # SDE数据服务
│   │   ├── picture_render_service/   # html生图服务
│   │   ├── resource/   # 静态资源
│   │   └── user_server/   # 用户管理模块
│   └── utils/             # 工具模块
├── data/                   # 数据库存放目录，可选用
├── config.ini.example     # 配置文件
├── main.py                # 插件入口
├── filter.py              # 权限过滤器
└── requirements.txt       # 依赖包列表
```

### 配置插件

#### 安装依赖

1. 安装pyppeteer
```bash
# 下载速度慢可以考虑使用加速源
pip install pyppeteer -i https://pypi.tuna.tsinghua.edu.cn/simple
```

2. 安装浏览器依赖
```bash
pyppeteer-install

apt-get install -y libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libatspi2.0-0
apt-get install -y fonts-noto-cjk fonts-noto-cjk-extra fonts-arphic-ukai fonts-arphic-uming

# 如果生成的图片中文都是方框，需要补充安装中文字体

```

#### 准备SDE数据库

- SDE数据库生成工具：**[EVE-SDE-Database-Builder](https://github.com/EVEIPH/EVE-SDE-Database-Builder.git)**
- 官方SDE数据库更新地址：**[https://developers.eveonline.com/](https://developers.eveonline.com/)**

使用数据库生成工具处理CCP官方发布的SDE数据库，输出英文和中文的SQLite版本数据库备用。

👇 参考下图 👇

![SDE数据库生成](https://github.com/user-attachments/assets/8db7c904-dbd7-4497-a0ad-efdc6358c58b)

#### 飞书API获取

1. 前往 **[飞书开发平台](https://open.feishu.cn/app)** 注册账号，并创建一个应用获取AppID和SecretID

   ![飞书开发平台](https://github.com/user-attachments/assets/3e321503-edaa-48f8-b964-5a2d39712a73)

   ![获取AppID和SecretID](https://github.com/user-attachments/assets/820341a3-c37d-42af-a67b-b05c0eed8706)

2. 添加机器人应用

   ![添加机器人应用](https://github.com/user-attachments/assets/310e6f16-93a1-45fc-b5d4-6d65b85814ba)

3. 开通应用权限，全选云文档权限即可

   ![开通应用权限](https://github.com/user-attachments/assets/e83653ed-3e72-4264-94a7-77ca751109fd)

4. 给机器人添加云文档权限 [如何为应用开通云文档相关资源的权限](https://open.feishu.cn/document/uAjLw4CM/ugTN1YjL4UTN24CO1UjN/trouble-shooting/how-to-add-permissions-to-app)

5. 新建一个云文档文件夹并获取链接，形式为`https://bcnzl0ndjqqq.feishu.cn/drive/folder/{folder_id}`，将folder_id记录

#### 修改配置文件

将`config.ini.example`复制一份，重命名为`config.ini`。

```ini
[APP]
DBTYPE = sqlite # 数据库类型，暂时只支持sqlite。本地数据库记得多备份哦~
COST_PLAN_USER = # 公共成本计算接口基准角色
COST_PLAN_NAME = # 公共成本计算接口基准角色名称
CORP_ASSET_USER =   # 
PIC_RENDER_PROXY =  # 图片渲染代理地址，默认为空，不使用代理

[FEISHU]
APP_ID = MyApp      # 飞书表格输出相关配置
SECRET_ID = 1.0     
FOLDER_ROOT = xxx   # 填入刚才获取的folder_id

[POSTGREDB]     # 暂未启用
Host = localhost
Port = 5432
User = admin
Password = secret

[SQLITEDB] # 数据库路径，填写绝对路径
CONFIG_DB = F:\path\to\kahuna.db
CACHE_DB = F:\path\to\cache.db
SDEDB = F:\path\to\sde.db           # 刚才获取的英文sde数据库
CN_SDEDB = F:\path\to\sde_cn.db     # 刚才获取的中文sde数据库

[EVE]   # eve相关配置，在https://developers.eveonline.com/申请应用获取
CLIENT_ID =
SECRET_KEY =
MARKET_AC_CHARACTER_ID=     # 玩家建筑市场访问角色id，先置空

[ESI]   # esi权限配置，需要和申请的应用保持一致，默认全部为true，意为全部权限，需要关闭的权限改为false。
publicData = true
esi-calendar.respond_calendar_events.v1 = true
esi-calendar.read_calendar_events.v1 = true
esi-location.read_location.v1 = true
esi-location.read_ship_type.v1 = true
esi-mail.organize_mail.v1 = true
......
```

## 关于工业规划如何使用的一份粗略的说明，先凑合用

👉 [小卡bot初级使用指南](https://conscious-cord-0d1.notion.site/bot-1920b0a9ac1b80998d71c4349b241145)

## TODO LIST
 - [x] QQbot开发
 - [ ] 网站开发
   - [ ] 前端开发
     - [ ] 框架
   - [x] esi访问队列控制
   - [ ] 数据库重构
     - [x] 部署postgre和redis

## 🌟 支持一下
求个star。
觉得好用的话，给孩子打点ISK呗~ 

`EVE_ID: Alero AraragiEro`

