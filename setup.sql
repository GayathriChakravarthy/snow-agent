-- Git API integration setup for connecting Workspaces to GitHub
-- Co-authored with CoCo

-- Create an API integration using the Snowflake GitHub App (no secrets required).
-- Users authenticate via browser-based OAuth when connecting a workspace.
CREATE OR REPLACE API INTEGRATION git_api_integration
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/GayathriChakravarthy')
  API_USER_AUTHENTICATION = (TYPE = SNOWFLAKE_GITHUB_APP)
  ENABLED = TRUE;

-- Create a secret to store your GitHub PAT
CREATE OR REPLACE SECRET INSURANCE_UNDERWRITING.PUBLIC.GIT_SECRET
  TYPE = password
  USERNAME = 'GayathriChakravarthy'
  PASSWORD = '<your-github-pat-here>';

-- Create API integration using the PAT secret
CREATE OR REPLACE API INTEGRATION git_api_integration
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/GayathriChakravarthy')
  ALLOWED_AUTHENTICATION_SECRETS = (INSURANCE_UNDERWRITING.PUBLIC.GIT_SECRET)
  ENABLED = TRUE;