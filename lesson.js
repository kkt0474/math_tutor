window.LESSON_DATA = {
  "viewConfig": {
    "hasAxes": false,
    "bounds": {
      "xmin": -1.5,
      "xmax": 10.5,
      "ymin": -1.5,
      "ymax": 9.5
    }
  },
  "questions": [
    {
      "title": "第(2)问：如图(3)，在四边形 $ABCD$ 中，$\\angle BAD = \\angle BCD = 60^\\circ$，$BC = CD$。过点 $C$ 分别作 $AB, AD$ 的垂线，垂足分别为 $M, N$。若 $BM = 2DN$，求 $\\frac{AB}{AD}$ 的值。",
      "thoughtAnalysis": "* **【💡 题眼信号识别（破题开关）】**：\n\n  原话信号一：“$BC = CD$ 且 $\\angle BCD = 60^\\circ$” →【破局开关：等边三角形残缺信号】。等腰三角形顶角为 $60^\\circ$，只要连接底边 $BD$，即可瞬间补全正三角形 $\\triangle BCD$，将孤立的两条相等线段连通为等边三角形，并获得核心基准角 $\\angle CBD = \\angle CDB = 60^\\circ$。\n\n  原话信号二：“$CM \\perp AB$，$CN \\perp AD$，$BM = 2DN$” →【破局开关：全等构造与线段转移】。外部已有两个直角三角形 $\\text{Rt}\\triangle BMC$ 与 $\\text{Rt}\\triangle DNC$，其斜边恰为等边三角形的边 $BC = CD$；已知条件 $BM = 2DN$ 分散在四边形外侧，必须通过在 $\\triangle ABD$ 内部作高构造全等三角形，把线段 $BM$ 与 $DN$ 转移到边 $AB$ 与 $AD$ 上。\n\n* **【🧭 人类解题思维路线】**：\n\n  1. 逆向探路（要求什么 → 缺什么）：要求 $\\frac{AB}{AD}$，但在 $\\triangle ABD$ 中只知道顶角 $\\angle BAD = 60^\\circ$，底边上的点 $B, D$ 与已知线段 $BM, DN$ 隔着外角，无法直接建立等量关系。\n\n  2. 顺向搭桥（角的实质转化）：连接 $BD$ 补全等边 $\triangle BCD$ 后，利用平角与四边形外角和定理，发现 $\\angle ABD$ 与 $\\angle CDN$ 互为等角的余角，精准推导出 $\\angle ABD = \\angle CDN$ 以及 $\\angle ADB = \\angle CBM$。\n\n  3. 构造全等（线段无损转移）：既然角相等且斜边 $BD = CD = BC$，从点 $D, B$ 分别向对边作垂线 $DP \\perp AB, BQ \\perp AD$，立即构造出两对 AAS 全等三角形，将分散在外的线段严丝合缝地转移为 $BP = DN$ 以及 $DQ = BM = 2BP$。\n\n  4. 逻辑闭环（初二特性代换）：最后在含 $60^\\circ$ 的 $\\text{Rt}\\triangle APD$ 与 $\\text{Rt}\\triangle AQB$ 中，运用“$30^\\circ$ 所对直角边等于斜边一半”建立 $AP = \\frac{1}{2}AD$ 与 $AQ = \\frac{1}{2}AB$，通过纯粹的线段等量替换，无需方程组与勾股定理，即可直接锁定 $\\frac{AB}{AD} = \\frac{4}{5}$。",
      "steps": [
        {
          "name": "原图呈现与已知条件梳理",
          "modelName": "四边形外角和与对角互补关联",
          "explanation": "观察原题图形，已知四边形 $ABCD$ 中 $\\angle BAD = 60^\\circ$，$\\angle BCD = 60^\\circ$，且 $BC = CD$。\n因为四边形内角和为 $360^\\circ$，所以内角和 $\\angle ABC + \\angle ADC = 360^\\circ - 60^\\circ - 60^\\circ = 240^\\circ$。\n因为点 $B, D$ 分别在直线 $AM, AN$ 上，所以外角和 $\\angle CBM + \\angle CDN = (180^\\circ - \\angle ABC) + (180^\\circ - \\angle ADC) = 360^\\circ - 240^\\circ = 120^\\circ$。\n结合已知垂直条件 $CM \\perp AM$，$CN \\perp AN$，==所以推得两个外角之和满足 $\\angle CBM + \\angle CDN = 120^\\circ$==",
          "ggbCommands": [
            "A = (0, 0)",
            "D = (6.54654, 0)",
            "N = (8.51052, 0)",
            "C = (8.51052, 5.66947)",
            "B = (2.61862, 4.53558)",
            "M = (4.58259, 7.93728)",
            "polyABCD = Polygon(A, B, C, D)",
            "SetColor(polyABCD, \"#38BDF8\")",
            "SetFillOpacity(polyABCD, 0.08)",
            "segAM = Segment(A, M)",
            "SetColor(segAM, \"#38BDF8\")",
            "segAN = Segment(A, N)",
            "SetColor(segAN, \"#38BDF8\")",
            "segCM = Segment(C, M)",
            "SetColor(segCM, \"#38BDF8\")",
            "segCN = Segment(C, N)",
            "SetColor(segCN, \"#38BDF8\")",
            "segBC = Segment(B, C)",
            "SetColor(segBC, \"#38BDF8\")",
            "SetDecoration(segBC, 1)",
            "segCD = Segment(C, D)",
            "SetColor(segCD, \"#38BDF8\")",
            "SetDecoration(segCD, 1)",
            "angA = Angle(D, A, B)",
            "SetColor(angA, \"#10B981\")",
            "ShowLabel(angA, false)",
            "angC = Angle(B, C, D)",
            "SetColor(angC, \"#10B981\")",
            "ShowLabel(angC, false)",
            "angM = Angle(B, M, C)",
            "SetColor(angM, \"#64748B\")",
            "ShowLabel(angM, false)",
            "angN = Angle(C, N, D)",
            "SetColor(angN, \"#64748B\")",
            "ShowLabel(angN, false)"
          ]
        },
        {
          "name": "连结 BD 构造等边三角形，实现角转换",
          "modelName": "等边三角形判定与平角等量代换",
          "explanation": "【💡 辅助线是怎么想到的？】观察图形发现已知条件 $BC = CD$ 且夹角 $\\angle BCD = 60^\\circ$，这是最典型的“知二补一”等边三角形信号！连接 $BD$ 即可直接构造出完整的等边 $\\triangle BCD$，从而将分散的线段转化为等边三角形的相等内角。\n因为 $BC = CD$ 且 $\\angle BCD = 60^\\circ$，所以 $\\triangle BCD$ 是等边三角形，得到 $BD = CD = BC$，且 $\\angle CBD = \\angle CDB = 60^\\circ$。\n因为点 $A, B, M$ 共线，所以平角 $\\angle ABM = \\angle ABD + \\angle CBD + \\angle CBM = 180^\\circ$。\n因为 $\\angle CBD = 60^\\circ$，所以得到 $\\angle ABD + \\angle CBM = 120^\\circ$。\n因为在 Step 1 中已证 $\\angle CDN + \\angle CBM = 120^\\circ$，所以两式等量代换得到 $\\angle ABD = \\angle CDN$。\n同理在平角 $\\angle ADN$ 上由 $\\angle ADB + \\angle CDB + \\angle CDN = 180^\\circ$，可推得 $\\angle ADB = \\angle CBM$。\n结合以上推导，==所以成功实现关键角转换，得到 $\\angle ABD = \\angle CDN$ 且 $\\angle ADB = \\angle CBM$==",
          "ggbCommands": [
            "segBD = Segment(B, D)",
            "SetLineStyle(segBD, 2)",
            "SetColor(segBD, \"#FACC15\")",
            "SetDecoration(segBD, 1)"
          ]
        },
        {
          "name": "作双垂线构造两对全等三角形",
          "modelName": "对称垂线模型与 AAS 全等转移线段",
          "explanation": "【💡 辅助线是怎么想到的？】我们要用已知条件 $BM = 2DN$，但 $BM$ 和 $DN$ 孤立在四边形外部；而在 Step 2 中我们已经发现关键等角 $\\angle ABD = \\angle CDN$ 与 $\\angle ADB = \\angle CBM$，且等边 $\\triangle BCD$ 提供了相等的斜边 $BD = CD = BC$。为了利用“等斜边与等锐角”构造全等，把外部线段转移到 $\\triangle ABD$ 的边上，我们自然想到过点 $D$ 作 $DP \\perp AB$ 于 $P$，过点 $B$ 作 $BQ \\perp AD$ 于 $Q$。\n在 $\\text{Rt}\\triangle BPD$ 和 $\\text{Rt}\\triangle DNC$ 中，因为 $\\angle BPD = \\angle DNC = 90^\\circ$，$\\angle PBD = \\angle CDN$，$BD = CD$，所以 $\\triangle BPD \\cong \\triangle DNC$ (AAS)，得到 $BP = DN$。\n在 $\\text{Rt}\\triangle BQD$ 和 $\\text{Rt}\\triangle CMB$ 中，因为 $\\angle BQD = \\angle BMC = 90^\\circ$，$\\angle BDQ = \\angle CBM$，$BD = BC$，所以 $\\triangle BQD \\cong \\triangle CMB$ (AAS)，得到 $DQ = BM$。\n因为已知 $BM = 2DN$，将全等对应边代入，得到 $DQ = 2BP$。\n结合以上推导，==所以成功将分散条件转移到边上，得到 $BP = DN$ 且 $DQ = 2BP$==",
          "ggbCommands": [
            "P = (1.63664, 2.83474)",
            "segDP = Segment(D, P)",
            "SetLineStyle(segDP, 2)",
            "SetColor(segDP, \"#FACC15\")",
            "angP = Angle(D, P, B)",
            "SetColor(angP, \"#FACC15\")",
            "ShowLabel(angP, false)",
            "Q = (2.61862, 0)",
            "segBQ = Segment(B, Q)",
            "SetLineStyle(segBQ, 2)",
            "SetColor(segBQ, \"#FACC15\")",
            "angQ = Angle(D, Q, B)",
            "SetColor(angQ, \"#FACC15\")",
            "ShowLabel(angQ, false)"
          ]
        },
        {
          "name": "利用 30° 直角三角形性质，等量替换锁定结论",
          "modelName": "含 30° 角直角三角形性质与代数式代换",
          "explanation": "在 $\\text{Rt}\\triangle APD$ 中，因为 $\\angle PAD = 60^\\circ$，所以锐角 $\\angle ADP = 30^\\circ$；根据直角三角形中 $30^\\circ$ 角所对直角边等于斜边一半，得到 $AP = \\frac{1}{2}AD$。\n在 $\\text{Rt}\\triangle AQB$ 中，因为 $\\angle QAB = 60^\\circ$，所以锐角 $\\angle ABQ = 30^\\circ$；同理得到 $AQ = \\frac{1}{2}AB$。\n由线段和差关系，边 $AB = AP + BP = \\frac{1}{2}AD + BP$，移项整理得到 $BP = AB - \\frac{1}{2}AD$。\n边 $AD = AQ + DQ = \\frac{1}{2}AB + DQ$，将 Step 3 证得的 $DQ = 2BP$ 代入，得到 $AD = \\frac{1}{2}AB + 2BP$。\n将 $BP = AB - \\frac{1}{2}AD$ 代入上式进行等量替换，化简得 $AD = \\frac{1}{2}AB + 2\\left(AB - \\frac{1}{2}AD\\right) = \\frac{5}{2}AB - AD$。\n两边同时加上 $AD$，整理得到 $2AD = \\frac{5}{2}AB$，即 $5AB = 4AD$。\n结合以上推导，==所以求得 $\\frac{AB}{AD}$ 的值为 $\\frac{4}{5}$==",
          "ggbCommands": [
            "polyAPD = Polygon(A, P, D)",
            "SetColor(polyAPD, \"#EC4899\")",
            "SetFillOpacity(polyAPD, 0.15)",
            "polyAQB = Polygon(A, Q, B)",
            "SetColor(polyAQB, \"#EAB308\")",
            "SetFillOpacity(polyAQB, 0.15)"
          ]
        }
      ],
      "solutionMarkdown": "#### 【中考规范书写过程】\n\n解：\n\n1. **构造等边三角形并转化角关系**：\n   连接 $BD$。\n   在 $\\triangle BCD$ 中，\n   $\\because BC = CD$ 且 $\\angle BCD = 60^\\circ$，\n   $\\therefore \\triangle BCD$ 为等边三角形。\n   $\\therefore BD = CD = BC$，且 $\\angle CBD = \\angle CDB = 60^\\circ$。\n\n2. **推导角相等关系**：\n   $\\because \\angle BAD = 60^\\circ$，$\\angle BCD = 60^\\circ$，四边形内角和为 $360^\\circ$，\n   $\\therefore \\angle ABC + \\angle ADC = 360^\\circ - 60^\\circ - 60^\\circ = 240^\\circ$。\n   $\\because A, B, M$ 共线，$A, D, N$ 共线，\n   $\\therefore$ 外角和 $\\angle CBM + \\angle CDN = (180^\\circ - \\angle ABC) + (180^\\circ - \\angle ADC) = 360^\\circ - 240^\\circ = 120^\\circ$。\n   又 $\\because \\angle ABD + \\angle CBD + \\angle CBM = 180^\\circ$ 且 $\\angle CBD = 60^\\circ$，\n   $\\therefore \\angle ABD + \\angle CBM = 120^\\circ$。\n   $\\therefore \\angle ABD = \\angle CDN$。\n   同理，$\\because \\angle ADB + \\angle CDB + \\angle CDN = 180^\\circ$ 且 $\\angle CDB = 60^\\circ$，\n   $\\therefore \\angle ADB + \\angle CDN = 120^\\circ$，\n   $\\therefore \\angle ADB = \\angle CBM$。\n\n3. **作辅助垂线证明全等**：\n   过点 $D$ 作 $DP \\perp AB$ 于点 $P$，过点 $B$ 作 $BQ \\perp AD$ 于点 $Q$。\n   在 $\\text{Rt}\\triangle BPD$ 与 $\\text{Rt}\\triangle DNC$ 中：\n   $$\\begin{cases} \\angle BPD = \\angle DNC = 90^\\circ \\\\ \\angle PBD = \\angle CDN \\\\ BD = CD \\end{cases}$$\n   $\\therefore \\triangle BPD \\cong \\triangle DNC\\text{ (AAS)}$。\n   $\\therefore BP = DN$。\n   在 $\\text{Rt}\\triangle BQD$ 与 $\\text{Rt}\\triangle CMB$ 中：\n   $$\\begin{cases} \\angle BQD = \\angle BMC = 90^\\circ \\\\ \\angle BDQ = \\angle CBM \\\\ BD = BC \\end{cases}$$\n   $\\therefore \\triangle BQD \\cong \\triangle CMB\\text{ (AAS)}$。\n   $\\therefore DQ = BM$。\n   $\\because BM = 2DN$，\n   $\\therefore DQ = 2BP$。\n\n4. **线段转化与求解**：\n   在 $\\text{Rt}\\triangle APD$ 中，$\\because \\angle APD = 90^\\circ$，$\\angle PAD = 60^\\circ$，\n   $\\therefore \\angle ADP = 30^\\circ$。\n   $\\therefore AP = \\frac{1}{2}AD$。\n   在 $\\text{Rt}\\triangle AQB$ 中，$\\because \\angle AQB = 90^\\circ$，$\\angle QAB = 60^\\circ$，\n   $\\therefore \\angle ABQ = 30^\\circ$。\n   $\\therefore AQ = \\frac{1}{2}AB$。\n   $\\because AB = AP + BP = \\frac{1}{2}AD + BP$，\n   $\\therefore BP = AB - \\frac{1}{2}AD$。\n   $\\because AD = AQ + DQ = \\frac{1}{2}AB + DQ = \\frac{1}{2}AB + 2BP$，\n   将 $BP = AB - \\frac{1}{2}AD$ 代入上式，得：\n   $$AD = \\frac{1}{2}AB + 2\\left(AB - \\frac{1}{2}AD\\right)$$\n   $$AD = \\frac{1}{2}AB + 2AB - AD$$\n   $$2AD = \\frac{5}{2}AB$$\n   $$5AB = 4AD$$\n   $\\therefore \\frac{AB}{AD} = \\frac{4}{5}$。"
    }
  ]
};
