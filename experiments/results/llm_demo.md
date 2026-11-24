# 本地大模型演示（Qwen2.5-0.5B-Instruct，CPU）

- 数据集：`movielens`
- 模型加载：34.3s
- 生成样本：6 条

| 用户 | 推荐物品 | LLM 生成理由 | 模板理由 | 延迟(s) |
|---|---|---|---|---|
| 414 | Everyone Says I Love You (1996) | 《Everyone Says I Love You》是一部以爱情为主题的喜剧电影，深受观众喜爱。 | 与你偏好的「Comedy、Romance」题材一致，且评分 3.5 | 13.32 |
| 414 | Edge, The (1997) | Edge, The (1997)，题材：Adventure|Drama，平均评分 3.0（11 人评分） | 综合协同信号与内容匹配度排序靠前，且评分 3.0 | 9.86 |
| 414 | Beneath the Planet of the Apes (1970) | 《 Beneath the Planet of the Apes (1970)》是剧情动作片，适合喜欢科幻和恐怖类型的用户。 | 与你偏好的「Action」题材一致，且评分 2.8 | 6.97 |
| 599 | Spy Who Loved Me, The (1977) | 《The》是20世纪最伟大的动作片之一，由詹姆斯·卡梅隆执导，杰森·斯坦森和凯瑟琳·赫本主演，是一部经典的科幻电影。 | 与你偏好的「Adventure」题材一致，且评分 3.4 | 8.66 |
| 599 | Tequila Sunrise (1988) | Tequila Sunrise (1988)，题材：Action|Drama|Romance|Thriller，平均评分 3.038（13 人评分） | 与你偏好的「Drama」题材一致，且评分 3.0 | 8.5 |
| 599 | The Revenant (2015) | 《Revenant》是一部以探险和复仇为主题的电影，剧情紧张刺激，值得一看。 | 与你偏好的「Adventure、Drama」题材一致，且评分 3.9 | 5.01 |

## LLM 重排输出

- 用户 414（3.61s）：
  - 基线：Everyone Says I Love You (1996) → Edge, The (1997) → Beneath the Planet of the Apes (1970) → Manhattan Murder Mystery (1993) → Mimic (1997) → George of the Jungle (1997)
  - LLM：Beneath the Planet of the Apes (1970) → Everyone Says I Love You (1996) → Edge, The (1997) → Manhattan Murder Mystery (1993) → George of the Jungle (1997) → Mimic (1997)
- 用户 599（4.06s）：
  - 基线：Spy Who Loved Me, The (1977) → Tequila Sunrise (1988) → The Revenant (2015) → Grudge, The (2004) → Fox and the Hound, The (1981) → Serendipity (2001)
  - LLM：The Revenant (2015) → Spy Who Loved Me, The (1977) → Tequila Sunrise (1988) → Grudge, The (2004) → Serendipity (2001) → Fox and the Hound, The (1981)