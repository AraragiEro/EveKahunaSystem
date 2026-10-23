// 定义定价方案接口
export interface PricingPlan {
  name: string
  price: string
  priceUnit: string
  /** 卡片顶部强调色，直接用 CSS 变量字符串，跟着主题走 */
  color: string
  features: Array<{
    category: string
    items: string[]
  }>
  isPopular?: boolean
  note?: string
  hasTrial?: boolean
  trialText?: string
}

// 定价方案数据
export const pricingPlans: PricingPlan[] = [
  {
    name: '免费用户',
    price: '免费',
    priceUnit: '',
    color: 'var(--k-color-text-secondary)',
    features: [
      {
        category: '零成本，即刻规划你的工业帝国',
        items: [
          '创建工业计划，从目标产物自动拆解制造链路',
          '流程视图：蓝图分解一目了然，复杂工序不再烧脑',
          '材料视图：原材料缺口清晰展示，缺什么心中有数',
          '工作流：生成可执行方案，支持类型筛选与部分接取',
          '采购视图：一键生成购物清单，批量采购效率翻倍',
        ]
      }
    ],
    isPopular: false,
    note: '升级 Alpha 解锁 ESI 库存集成与数据面板'
  },
  {
    name: 'Alpha 订阅',
    price: '500M',
    priceUnit: 'ISK / 月',
    color: 'var(--k-color-primary)',
    note: '提示：添加公司库存需要总监权限',
    features: [
      {
        category: '连接游戏 · 告别手动对账',
        items: [
          '配置目标容器，实时读取角色库存与蓝图数据',
          '流程视图自动比对库存，精准判断制造进度',
          '工作流自动检测材料缺口与蓝图缺失，不再盲做',
        ]
      },
      {
        category: '数据看板 · 一眼掌控全局',
        items: [
          '资产总览：钱包、订单、运行中任务集中展示',
          '订单统计：按日/周/月追踪买卖数量与收益',
          '历史趋势：资产曲线自动记录，看清每一分钱的去向',
        ]
      },
      {
        category: '高级报表 · 深度优化生产',
        items: [
          '成本视图：成分比例分析，找准降本空间',
          '劳动力视图：分工贡献一目了然，合作分钱不再扯皮',
          '物流视图：材料运输方案，起止地筛选直达',
          '化矿求解：矿石配平优化，支持溢价、运费等高级参数',
        ]
      }
    ],
    isPopular: true
  },
  {
    name: 'Omega 订阅',
    price: '2B',
    priceUnit: 'ISK / 月',
    color: 'var(--k-color-warning)',
    hasTrial: true,
    trialText: '可领取 7 天试用',
    features: [
      {
        category: '市场分析 · 让数据变成利润',
        items: [
          '自选物品清单，Jita 与 FRT 双市场行情实时监控',
          '结合你的制造计划，自动计算成本与预期利润',
          '价格与成本历史追踪，把握最佳买卖时机',
          '交易量与流水分析，一眼看穿市场热度',
        ]
      },
      {
        category: '效率工具 · 省时省力',
        items: [
          '批量添加工业计划，多产物一键配置',
          '成本视图集成实时市场价格，利润算得更准',
        ]
      }
    ],
    isPopular: false
  }
]
