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
    },
]