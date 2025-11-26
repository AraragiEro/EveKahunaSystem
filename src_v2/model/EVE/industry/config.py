DEFAULT_MATERIAL_CONFIG = [
    {
        # 矿物
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
    {
        # 元素
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
    {
        # 气云
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
    {
        # 冰矿产物
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
    {
        # 行星工业
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
    {
        # R.A.M.
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
    }
]

DEFAULT_BLUEPRINT_CONFIG = [
    {
        # T2默认蓝图效率
        "config_type": "DefaultBlueprintConf",
        "config_value": {
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
            ],
            "mater_eff": 2,
            "time_eff": 4
        }
    },
    {
        # T1船默认蓝图效率
        "config_type": "DefaultBlueprintConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Tech I",
                    "keyword_type": "meta"
                },
                {
                    "index": 1,
                    "keyword": "Ships",
                    "keyword_type": "marketGroup"
                }
            ],
            "mater_eff": 10,
            "time_eff": 20
        }
    },
    {
        # 反应材料效率
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
    {
        # 所有材料效率
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
]

DEFAULT_STRUCTURE_ASSIGN_CONFIG = [
    # 建筑分配
    {
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "Ships",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo"
        }
    },
    {
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                    "index": 0,
                    "keyword": "制造和研究",
                    "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Sotiyo"
        }
    },
    {
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "反应材料",
                "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Tatara"
        }
    },
    {
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "高级组件",
                "keyword_type": "marketGroup"
                }
            ],
            "structure_name": "虚拟-Raitaru"
        }
    },
    {
        "config_type": "StructureAssignConf",
        "config_value": {
            "keyword_groups": [
                {
                "index": 0,
                "keyword": "防护性组件",
                "keyword_type": "marketGroup"
                }
            ],
        "structure_name": "虚拟-Raitaru"
        }
    }
]

DEFAULT_STRUCTURE_RIG_CONFIG = [
    # 建筑插
    # T1虚拟STY
    {
        "config_type": "StructureRigConfig",
        "config_value": {
            "structure_id": 1,
            "time_eff_level": 1,
            "mater_eff_level": 1
        }
    },
    # T2虚拟TRR
    {
        "config_type": "StructureRigConfig",
        "config_value": {
            "structure_id": 2,
            "time_eff_level": 2,
            "mater_eff_level": 2
        }
    },
    # T2虚拟莱塔卢
    {
        "config_type": "StructureRigConfig",
        "config_value": {
            "structure_id": 3,
            "time_eff_level": 2,
            "mater_eff_level": 2
        }
    }
]

DEFAULT_MAX_JOB_SPLIT_COUNT_CONFIG = [
    # 流程分割
    # 反应
    {
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
    {
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
    {
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
    {
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
    {
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
]