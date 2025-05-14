# "データと会話する" エージェント

「データと会話する」エージェントは、あなたがデータと対話できる環境を提供します。CSVファイルをアップロードし、質問をすると、エージェントはビジネス分析を提案します。その後、質問に答えるためのグラフや表（ソースコードを含む）を作成します。この体験は、MLOpsと連携し、コンポーネントのホスティング、監視、管理を行います。

> [!WARNING]
> Application templates are intended to be starting points that provide guidance on how to develop, serve, and maintain AI applications.
> They require a developer or data scientist to adapt and modify them for their business requirements before being put into production.

![Using the "Talk to my data" agent](https://s3.us-east-1.amazonaws.com/datarobot_public/drx/recipe_gifs/launch_gifs/talktomydata.gif)


## Table of contents
1. [Setup](#setup)
2. [Architecture overview](#architecture-overview)
3. [Why build AI Apps with DataRobot app templates?](#why-build-ai-apps-with-datarobot-app-templates)
4. [Data privacy](#data-privacy)
5. [Make changes](#make-changes)
   - [Change the LLM](#change-the-llm)
   - [Change the database](#change-the-database)
      * [No database](#no-database)
      * [BigQuery](#bigquery)
6. [Share results](#share-results)
7. [Delete all provisioned resources](#delete-all-provisioned-resources)
8. [Setup for advanced users](#setup-for-advanced-users)

## Setup

開始する前に、必要な資格情報とサービスへのアクセス権があることを確認してください。このテンプレートは、Azure OpenAIエンドポイントとSnowflakeデータベースの資格情報を使用するように事前に構成されています。テンプレートをそのまま実行するには、Azure OpenAI（デフォルトで`gpt-4o`を活用）へのアクセス権が必要です。

Codespacesユーザーは**ステップ1と2をスキップ**できます。ローカル開発の場合は、以下のすべてのステップに従ってください。

1. `pulumi`がまだインストールされていない場合は、[こちら](https://www.pulumi.com/docs/iac/download-install/)の指示に従ってCLIをインストールします。
   初めてインストールした後は、ターミナルを再起動し、以下を実行します。
   ```bash
   pulumi login --local  # Pulumi Cloudを使用する場合は--localを省略（別途アカウントが必要）
   ```

2. テンプレートリポジトリをクローンします。

   ```bash
   git clone https://github.com/ShogoNagano/talk-to-my-data-agent.git #ハンズオンはこちら
   #git clone https://github.com/datarobot-community/talk-to-my-data-agent.git #本家はこちら
   cd talk-to-my-data-agent
   ```

3. リポジトリのルートディレクトリにある`.env.template`ファイルを`.env`に名前変更し、資格情報を入力します。

   ```bash
   DATAROBOT_API_TOKEN=...
   DATAROBOT_ENDPOINT=...  # e.g. https://app.jp.datarobot.com/api/v2
   OPENAI_API_KEY=...
   OPENAI_API_VERSION=...  # e.g. 2024-02-01
   OPENAI_API_BASE=...  # e.g. https://your_org.openai.azure.com/
   OPENAI_API_DEPLOYMENT_ID=...  # e.g. gpt-4o
   PULUMI_CONFIG_PASSPHRASE=...  # Required. Choose your own alphanumeric passphrase to be used for encrypting pulumi config
   ```
  必要な資格情報の場所については、以下のリソースを参照してください:
   - **DataRobot API Token**: Refer to the *Create a DataRobot API Key* section of the [DataRobot API Quickstart docs](https://docs.datarobot.com/en/docs/api/api-quickstart/index.html#create-a-datarobot-api-key).
   - **DataRobot Endpoint**: Refer to the *Retrieve the API Endpoint* section of the same [DataRobot API Quickstart docs](https://docs.datarobot.com/en/docs/api/api-quickstart/index.html#retrieve-the-api-endpoint).
   - **LLM Endpoint and API Key**: Refer to the [Azure OpenAI documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/chatgpt-quickstart?tabs=command-line%2Cjavascript-keyless%2Ctypescript-keyless%2Cpython-new&pivots=programming-language-python#retrieve-key-and-endpoint).

4. ターミナルで、以下を実行します:
   ```bash
   python quickstart.py YOUR_PROJECT_NAME  # Windows users may have to use `py` instead of `python`
   ```
   Python 3.9以降が必要です。


仮想環境の作成、依存関係のインストール、環境変数の設定、および`pulumi`の呼び出しを制御したい高度なユーザーは、
[こちら](#setup-for-advanced-users)を参照してください。

## Architecture overview

![Image](https://github.com/user-attachments/assets/60f788c0-c017-4092-aa7c-b047afdd9d5f)


アプリテンプレートには、3つの補完的なロジックファミリーが含まれています:

- **AI logic**: AIリクエストを処理し、予測と完了を生成するために必要です。
  ```
  deployment_*/  # Chat agent model
  ```
- **App Logic**: ホストされたフロントエンド経由でも、外部の利用層に統合する場合でもユーザーが利用するために必要です。
  ```
  frontend/  # Streamlit frontend
  utils/  # App business logic & runtime helpers
  ```
- **Operational Logic**: DataRobotアセットをアクティブ化するために必要です。
  ```
  infra/__main__.py  # Pulumi program for configuring DataRobot to serve and monitor AI and app logic
  infra/  # Settings for resources and assets created in DataRobot
  ```

## Why build AI Apps with DataRobot app templates?

アプリテンプレートは、AIプロジェクトをノートブックから本番環境対応のアプリケーションに変えます。モデルを本番環境に移行するには、コードの書き換え、資格情報の管理、単純な変更を行うだけでも複数のツールとチームとの連携が必要になることがよくあります。DataRobotの構成可能なAIアプリフレームワークは、これらのボトルネックを解消し、接続やデプロイに苦労する時間を減らし、MLとアプリロジックの実験に時間を費やすことができます。
- 数分で構築を開始: 完全なAIアプリケーションを即座にデプロイし、その後、AIロジックまたはフロントエンドを個別にカスタマイズできます（アーキテクチャの書き換えは不要）。
- 自分のやり方を維持: データサイエンティストはノートブックで、開発者はIDEで作業を続け、構成は分離されたままになります。他の部分を壊すことなく、任意の部分を更新できます。
- 安心して反復処理: ローカルで変更を加え、自信を持ってデプロイできます。配管の記述とトラブルシューティングにかかる時間を減らし、アプリの改善に時間を費やすことができます。

各テンプレートは、生データの入力からデプロイされたアプリケーションまで、エンドツーエンドのAIアーキテクチャを提供し、特定のビジネス要件に合わせて高度にカスタマイズ可能です。

## Data privacy
Your data privacy is important to us. Data handling is governed by the DataRobot [Privacy Policy](https://www.datarobot.com/privacy/), please review before using your own data with DataRobot.


## Make changes

### Change the LLM

1. Modify the `LLM` setting in `infra/settings_generative.py` by changing `LLM=GlobalLLM.AZURE_OPENAI_GPT_4_O` to any other LLM from the `GlobalLLM` object. 
     - Trial users: Please set `LLM=GlobalLLM.AZURE_OPENAI_GPT_4_O_MINI` since GPT-4o is not supported in the trial. Use the `OPENAI_API_DEPLOYMENT_ID` in `.env` to override which model is used in your azure organisation. You'll still see GPT 4o-mini in the playground, but the deployed app will use the provided azure deployment.  
2. Provide the required credentials in `.env` dependent on your choice.
3. Run `pulumi up` to update your stack (Or rerun your quickstart).
      ```bash
      source set_env.sh  # On windows use `set_env.bat`
      pulumi up
      ```

### Change the database

#### No database

データベース接続を完全に削除するには:

1. `infra/settings_database.py`の`DATABASE_CONNECTION_TYPE`設定を`DATABASE_CONNECTION_TYPE="snowflake"`から `DATABASE_CONNECTION_TYPE="no_database"`に変更します。
 
#### BigQuery

データと会話するエージェントは、BigQueryへの接続をサポートしています.
1. `infra/settings_database.py`の`DATABASE_CONNECTION_TYPE`設定を`DATABASE_CONNECTION_TYPE="snowflake"`から`DATABASE_CONNECTION_TYPE=bigquery`に変更します. 
2. 選択に応じて、`.env`に必要なGoogle資格情報を入力します。`.env`にGOOGLE_DB_SCHEMAも入力されていることを確認してください.
3. `pulumi up`を実行してスタックを更新します（またはクイックスタートを再実行します）。
      ```bash
      source set_env.sh  # On windows use `set_env.bat`
      pulumi up
      ```

## Share results

1. DataRobotアプリケーションにログインします。
2. **Registry > Applications**に移動します。
3. 共有したいアプリケーションに移動し、アクションメニューを開き、ドロップダウンから**Share**を選択します。

## Delete all provisioned resources

```bash
pulumi down
```

## Setup for advanced users
設定プロセスを手動で制御するには、以下の手順をMacOS/Linux環境に合わせて調整してください:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
source set_env.sh
pulumi stack init YOUR_PROJECT_NAME
pulumi up 
```
例：Windows/conda/cmd.exeの場合:
```bash
conda create --prefix .venv pip
conda activate .\.venv
pip install -r requirements.txt
set_env.bat
pulumi stack init YOUR_PROJECT_NAME
pulumi up
```
こちらのリポジトリは元のDataRobotプロジェクトからフォークしたものなので最新の機能が反映されていない可能性があります。
