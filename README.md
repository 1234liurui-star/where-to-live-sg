# Where to Live SG - web app (version 3)

## 文件夹里有什么
- app.py            网页本身（Streamlit）
- onemap.py         调用 OneMap：地址联想搜索、查公交时间、短途查步行时间（周二 08:00 出发）
- rent.py           从 rent_contracts.csv 算典型租金、常见区间、预算内租约数
- tools/build_rent_data.py   重建租金数据（所有房型）：用 URA 下载文件，或用 URA API
- .github/workflows/update-rent.yml   每季度自动运行 build_rent_data.py api（需要 URA key）
- data/candidates.csv      候选区
- data/rent_contracts.csv  租金合同（由 build_rent_data.py 生成）
- requirements.txt

## 全岛版本：第一次要运行的两个命令（在 wheretolive 文件夹里）
1. keys.txt 里要有三行：ONEMAP_EMAIL=…、ONEMAP_PASSWORD=…、URA_ACCESS_KEY=…
2. 生成全岛 MRT 站列表（约 3 分钟）：
       python tools/build_candidates.py
3. 用 URA API 拉全岛、所有房型的租约（几分钟）：
       python tools/build_rent_data.py api
4. 把 data 文件夹里的 candidates.csv、rent_contracts.csv、rent_build_info.json、rent_build_log.txt
   上传到 GitHub 替换旧文件。

## 本地运行
    python -m pip install -r requirements.txt
    python -m streamlit run app.py

## 加上 1 房、4 房：用你已经下载的 URA 文件重建数据
1. 在 tools 文件夹里新建 ura_downloads 文件夹，把 Gate 2 的 URA 下载文件全部放进去。
2. 把 Gate 2 的 project_locations.csv 复制到 tools 文件夹（这样不用重新给项目定位）。
3. 在 wheretolive 文件夹里运行：
       python tools/build_rent_data.py downloads
4. 生成新的 data/rent_contracts.csv 后，上传到 GitHub 替换旧文件。网页的房间数选项会自动变成数据里有的所有房型。

## 每季度自动更新（要 URA key 能用）
1. GitHub 仓库 > Settings > Secrets and variables > Actions > New repository secret，加三个：
   URA_ACCESS_KEY、ONEMAP_EMAIL、ONEMAP_PASSWORD
2. 把 .github/workflows/update-rent.yml 放进仓库（同样的路径）。
3. 每年 2、5、8、11 月 15 日会自动运行；也可以在 Actions 页面点 Run workflow 手动跑一次测试。
4. 运行记录写在 data/rent_build_log.txt，网页底部会显示数据来源和更新时间。

## 规则
- 每个数字都有来源。查不到写 NOT FOUND，不估算。不排名，家庭自己取舍。
- 房源链接只是打开 PropertyGuru 的搜索页，不收任何费用或佣金。
