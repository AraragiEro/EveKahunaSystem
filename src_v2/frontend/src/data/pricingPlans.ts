// 定义定价方案接口
export interface PricingPlan {
  name: string
  price: string
  priceUnit: string
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
    color: '#909399',
    features: [
      {
        category: '完整的工业流程计算相关功能',
        items: [
          '完整的计划功能',
          '除esi库存读取外的计划配置功能',
          '报表解锁',
          '  • 流程视图：详细的蓝图分解',
          '  • 材料视图：原材料的缺失情况',
          '  • 工作流：可执行的工作方案',
          '  • 采购视图：可进行一键采购的清单'
        ]
      }
    ],
    isPopular: false
  },
  {
    name: 'Alpha订阅',
    price: '500M',
    priceUnit: 'Isk/月',
    color: '#409eff',
    note: '注意：需要有总监权限才可以添加公司库存',
    features: [
      {
        category: '免费用户的所有功能',
        items: []
      },
      {
        category: '工业流程计算功能附加esi读取能力',
        items: [
          '可以配置想要读取的目标容器',
          '流程视图根据库存判断工作进度',
          '工作流根据库存判断原材料是否满足与蓝图是否缺失',
          '+ 成本视图：分析成本分布比例判断盈利空间',
          '+ 劳动力视图：提供输出向计划容器的所有正在进行的工作者信息，提供合作利益分配手段',
          '+ 物流视图：提供材料满足但是需要运输时的可执行方案',
          '+ 化矿视图：对矿石配平求解'
        ]
      }
    ],
    isPopular: true
  },
  {
    name: 'Omega订阅',
    price: '2B',
    priceUnit: 'Isk/月',
    color: '#e6a23c',
    hasTrial: true,
    trialText: '可领取7天试用',
    features: [
      {
        category: '免费用户与alpha订阅的全部功能',
        items: []
      },
      {
        category: '市场分析与利润分析',
        items: [
          '创建自选type的市场监控界面',
          '可选jita与FRT市场的价格拉取',
          '根据你的计划配置计算type成本与利润',
          '对单个type或清单内全量type的交易量、流水等分析（开发中）'
        ]
      }
    ],
    isPopular: false
  }
]
