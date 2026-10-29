# Where to Live SG - web app (version 1)

## 文件夹里有什么
- app.py            网页本身（Streamlit）
- onemap.py         调用 OneMap：找地址、查公交时间、短途查步行时间（周二 08:00 出发）
- rent.py           从 rent_contracts.csv 算租金的 25% / 中位数 / 75% 和预算内合同数
- data/candidates.csv      10 个候选区和查询用的名字（可以换成你 Gate 2 的 candidates.csv）
- data/rent_contracts.csv  需要你放进来：Gate 2 rent_manual.py 生成的那个文件
- requirements.txt  需要安装的包
- .streamlit/config.toml  页面颜色

## 第一步：在自己电脑上运行
1. 把 Gate 2 的 rent_contracts.csv 复制到 data 文件夹。
2. 把 keys.txt（OneMap 账号密码）复制到 app.py 旁边。
3. 打开命令提示符，进入这个文件夹，运行：
       pip install -r requirements.txt
       streamlit run app.py
4. 浏览器会自动打开网页。填好家庭需求，点 Compare areas。

## 第二步：上线（Streamlit Community Cloud，免费）
1. 在 GitHub 新建一个仓库，把这个文件夹传上去。
   keys.txt 不要上传（.gitignore 已经挡住了）。
2. 打开 share.streamlit.io，用 GitHub 登录，New app，选这个仓库，主文件填 app.py。
3. 在 App settings > Secrets 里填：
       ONEMAP_EMAIL = "你的邮箱"
       ONEMAP_PASSWORD = "你的密码"
4. 点 Deploy，几分钟后得到一个网址。

## 规则（和 Gate 2 一样）
- 每个数字都有来源，页面下方 "Sources" 里能看到每一条 OneMap 查询。
- 查不到就写 NOT FOUND，不估算。
- 不排名，家庭自己取舍。
- rent.py 里的 MIN_CONTRACTS 要和 rent_manual.py 里的值一样。
