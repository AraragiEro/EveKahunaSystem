DEFAULT_MATERIAL_CONFIG = {
    "预设原材料-矿物": {
        # 矿物
        "config_tag": "预设原材料-矿物",
        "config_type": "MaterialTagConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "矿物",
                "keyword_type": "marketGroup"
                }
            ]
        }
    },
    "预设原材料-元素": {
        # 元素
        "config_tag": "预设原材料-元素",
        "config_type": "MaterialTagConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "卫星原材料",
                "keyword_type": "marketGroup"
                }
            ]
        }
    },
    "预设原材料-气云": {
        # 气云
        "config_tag": "预设原材料-气云",
        "config_type": "MaterialTagConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "Gas Clouds Materials",
                "keyword_type": "marketGroup"
                }
            ]
            }
    },
    "预设原材料-冰矿产物": {
        # 冰矿产物
        "config_tag": "预设原材料-冰矿产物",
        "config_type": "MaterialTagConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "Ice Products",
                "keyword_type": "marketGroup"
                }
            ]
        }
    },
    "预设原材料-行星工业": {
        # 行星工业
        "config_tag": "预设原材料-行星工业",
        "config_type": "MaterialTagConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "Planetary Materials",
                "keyword_type": "marketGroup"
                }
            ]
        }
    },
    "预设原材料-R.A.M.": {
        # R.A.M.
        "config_tag": "预设原材料-R.A.M.",
        "config_type": "MaterialTagConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "R.A.M.",
                "keyword_type": "marketGroup"
                }
            ]
        }
    },
    "预设原材料-燃料块": {
        # 燃料块
        "config_tag": "预设原材料-燃料块",
        "config_type": "MaterialTagConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "Fuel Blocks",
                "keyword_type": "marketGroup"
                }
            ]
        }
    }
}

DEFAULT_BLUEPRINT_CONFIG = {
    "预设蓝图效率-T2-2/4": {
        # T2默认蓝图效率
        "config_tag": "预设蓝图效率-T2-2/4",
        "config_type": "DefaultBlueprintConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "Tech II",
                "keyword_type": "meta"
                }
            ],
            "mater_eff": 2,
            "time_eff": 4
        }
    },
    "预设蓝图效率-T1-10/20": {
        # T1船默认蓝图效率
        "config_tag": "预设蓝图效率-T1-10/20",
        "config_type": "DefaultBlueprintConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Tech I",
                    "keyword_type": "meta"
                }
            ],
            "mater_eff": 10,
            "time_eff": 20
        }
    },
    "预设蓝图效率-势力船-0/0": {
        # 势力船蓝图效率
        "config_tag": "预设蓝图效率-势力船-0/0",
        "config_type": "DefaultBlueprintConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Faction",
                    "keyword_type": "meta"
                }
            ],
            "mater_eff": 0,
            "time_eff": 0
        }
    },
    "预设蓝图效率-小旗舰-9/18": {
        # 小旗舰蓝图效率
        "config_tag": "预设蓝图效率-小旗舰-9/18",
        "config_type": "DefaultBlueprintConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Small Flagships",
                    "keyword_type": "marketGroup"
                }
            ],
            "mater_eff": 9,
            "time_eff": 18
        }
    },
    "预设蓝图效率-超旗-8/16": {
        # 超旗蓝图效率
        "config_tag": "预设蓝图效率-超旗-8/16",
        "config_type": "DefaultBlueprintConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Super Flagships",
                    "keyword_type": "marketGroup"
                }
            ],
            "mater_eff": 8,
            "time_eff": 16
        }
    },
    "预设蓝图效率-反应-0/0": {
        # 反应材料效率
        "config_tag": "预设蓝图效率-反应-0/0",
        "config_type": "DefaultBlueprintConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Reaction Materials",
                    "keyword_type": "marketGroup"
                }
            ],
            "mater_eff": 0,
            "time_eff": 0
        }
    },
    "预设蓝图效率-制造与研究(兜底)-10/20": {
        # 所有材料效率
        "config_tag": "预设蓝图效率-制造与研究(兜底)-10/20",
        "config_type": "DefaultBlueprintConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "制造和研究",
                    "keyword_type": "marketGroup"
                }
            ],
            "mater_eff": 10,
            "time_eff": 20
        }
    }
}

DEFAULT_STRUCTURE_ASSIGN_CONFIG = {
    # 建筑分配
    "预设建筑分配-船-T1STY": {
        # 船分配
        "config_tag": "预设建筑分配-船-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Ships",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-船装备-T1STY": {
        # 船装备
        "config_tag": "预设建筑分配-船装备-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Ship Equipment",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-建筑装备-T1STY": {
        # 建筑装备
        "config_tag": "预设建筑分配-建筑装备-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Structure Equipment",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-船插-T1STY": {
        # 船插
        "config_tag": "预设建筑分配-船插-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Ship and Module Modifications",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-建筑插-T1STY": {
        # 建筑插
        "config_tag": "预设建筑分配-建筑插-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Structure Modifications",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-中间产物-T1STY": {
        # 制造与研究分配
        "config_tag": "预设建筑分配-中间产物-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "制造和研究",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-无人机-T1STY": {
        # 无人机
        "config_tag": "预设建筑分配-无人机-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Drones",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-弹药-T1STY": {
        # 弹药
        "config_tag": "预设建筑分配-弹药-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Ammunition & Charges",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-脑插-T1STY": {
        # 脑插
        "config_tag": "预设建筑分配-脑插-T1STY",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Implants",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo",
            "structure_id": 1
        }
    },
    "预设建筑分配-反应材料-T2TRR": {
        # 反应材料
        "config_tag": "预设建筑分配-反应材料-T2TRR",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "反应材料",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Tatara",
            "structure_id": 2
        }
    },
    "预设建筑分配-组件-T2Raitaru": {
        # 组件
        "config_tag": "预设建筑分配-组件-T2Raitaru",
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Components",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Raitaru",
            "structure_id": 3
        }
    }
}

DEFAULT_STRUCTURE_RIG_CONFIG = {
    # 建筑插
    # T1虚拟STY
    "预设建筑插件-T1虚拟STY": {
        # T1虚拟STY
        "config_tag": "预设建筑插件-T1虚拟STY",
        "config_type": "StructureRigConfig",
        "config_value": {
            "structure_id": 1,
            "time_eff_level": 1,
            "mater_eff_level": 1
        }
    },
    # T2虚拟TRR
    "预设建筑插件-T2虚拟TRR": {
        # T2虚拟TRR
        "config_tag": "预设建筑插件-T2虚拟TRR",
        "config_type": "StructureRigConfig",
        "config_value": {
            "structure_id": 2,
            "time_eff_level": 2,
            "mater_eff_level": 2
        }
    },
    # T2虚拟莱塔卢
    "预设建筑插件-T2虚拟莱塔卢": {
        # T2虚拟莱塔卢
        "config_tag": "预设建筑插件-T2虚拟莱塔卢",
        "config_type": "StructureRigConfig",
        "config_value": {
            "structure_id": 3,
            "time_eff_level": 2,
            "mater_eff_level": 2
        }
    }
}

DEFAULT_MAX_JOB_SPLIT_COUNT_CONFIG = {
    # 流程分割
    # 反应
    "预设作业拆分-反应-60流程": {
        # 反应
        "config_tag": "预设作业拆分-反应-60流程",
        "config_type": "MaxJobSplitCountConf",
        "config_value": {
            "max_count": 60,
            "judge_type": "count",
            "max_time_day": 0,
            "max_time_date": "",
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Reaction Materials",
                    "keyword_type": "marketGroup"
                }
            ]
        }
    },
    # T2船
    "预设作业拆分-T2船-1流程": {
        # T2船
        "config_tag": "预设作业拆分-T2船-1流程",
        "config_type": "MaxJobSplitCountConf",
        "config_value": {
            "max_count": 1,
            "judge_type": "count",
            "max_time_day": 0,
            "max_time_date": "",
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "Tech II",
                "keyword_type": "meta"
                },
                {
                "index": 1,
                "keyword": "Ships",
                "keyword_type": "marketGroup"
                }
            ]
        }
    },
    # 船
    "预设作业拆分-船-10流程": {
        # 船
        "config_tag": "预设作业拆分-船-10流程",
        "config_type": "MaxJobSplitCountConf",
        "config_value": {
            "max_count": 10,
            "judge_type": "count",
            "max_time_day": 0,
            "max_time_date": "",
            "keyword_groups": [
                {
                "index": 1,
                "keyword": "Ships",
                "keyword_type": "marketGroup"
                }
            ]
        }
    },
    # 制造兜底时间控制
    "预设作业拆分-制造兜底-3天6小时": {
        # 制造兜底时间控制
        "config_tag": "预设作业拆分-制造兜底-3天6小时",
        "config_type": "MaxJobSplitCountConf",
        "config_value": {
            "max_count": 0,
            "judge_type": "time",
            "max_time_day": 3,
            "max_time_date": "00:06:00",
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "制造和研究",
                "keyword_type": "marketGroup"
                }
            ]
        }
    },
    # 标准旗舰组件
    "预设作业拆分-标准旗舰组件-40流程": {
        # 标准旗舰组件
        "config_tag": "预设作业拆分-标准旗舰组件-40流程",
        "config_type": "MaxJobSplitCountConf",
        "config_value": {
            "max_count": 40,
            "judge_type": "count",
            "max_time_day": 0,
            "max_time_date": "",
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "旗舰组件",
                    "keyword_type": "marketGroup"
                }
            ]
        }
    }
}

DEFAULT_ALL_CONFIG_FLOW_PRESET = [
    # 建筑插
    "预设建筑插件-T1虚拟STY",
    "预设建筑插件-T2虚拟TRR",
    "预设建筑插件-T2虚拟莱塔卢",
    # 建筑分配
    "预设建筑分配-船-T1STY",
    "预设建筑分配-船装备-T1STY",
    "预设建筑分配-建筑装备-T1STY",
    "预设建筑分配-船插-T1STY",
    "预设建筑分配-建筑插-T1STY",
    "预设建筑分配-中间产物-T1STY",
    "预设建筑分配-无人机-T1STY",
    "预设建筑分配-弹药-T1STY",
    "预设建筑分配-脑插-T1STY",
    "预设建筑分配-反应材料-T2TRR",
    "预设建筑分配-组件-T2Raitaru",
    # 原材料标记
    "预设原材料-矿物",
    "预设原材料-元素",
    "预设原材料-气云",
    "预设原材料-冰矿产物",
    "预设原材料-行星工业",
    "预设原材料-R.A.M.",
    "预设原材料-燃料块",
    # 缺省蓝图参数
    "预设蓝图效率-反应-0/0",
    "预设蓝图效率-势力船-0/0",
    "预设蓝图效率-T2-2/4",
    "预设蓝图效率-小旗舰-9/18",
    "预设蓝图效率-超旗-8/16",
    "预设蓝图效率-T1-10/20",
    "预设蓝图效率-制造与研究(兜底)-10/20",
    # 最大作业拆分
    "预设作业拆分-反应-60流程",
    "预设作业拆分-T2船-1流程",
    "预设作业拆分-标准旗舰组件-40流程",
    "预设作业拆分-船-10流程",
    "预设作业拆分-制造兜底-3天6小时",
]