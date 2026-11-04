import json
import tempfile
import unittest
from pathlib import Path

from codex_bootstrap.catalog import RULES, bundled_candidates
from codex_bootstrap.profile import profile_repo
from codex_bootstrap.selection import Candidate, rejection


class ProfileV12Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_database_libraries_preserve_identity_without_engine_versions(self):
        self.write(
            "package.json",
            json.dumps(
                {
                    "dependencies": {
                        "pg": "^8.13.0",
                        "redis": "^5.0.0",
                        "better-sqlite3": "^11.0.0",
                    }
                }
            ),
        )
        self.write("requirements.txt", "psycopg==3.2.1\npsycopg2==2.9.9\nredis==5.2.1\n")
        self.write(
            "Cargo.toml",
            '[package]\nname="app"\nversion="0.1.0"\n[dependencies]\nrusqlite="0.32"\n',
        )
        self.write("go.mod", "module app\ngo 1.23\nrequire github.com/jackc/pgx/v5 v5.7.0\n")
        self.write(
            "package-lock.json",
            json.dumps(
                {
                    "packages": {
                        "node_modules/pg": {"version": "8.13.1"},
                        "node_modules/redis": {"version": "5.1.0"},
                    }
                }
            ),
        )
        profile = profile_repo(self.root)
        for engine in ("postgres", "redis", "sqlite"):
            self.assertEqual(profile.technologies[engine], "detected")
            self.assertNotIn(engine, profile.resolved_versions)
            self.assertTrue(
                all(s["version"] == "detected" for s in profile.technology_sources[engine])
            )
        for package in (
            "pg",
            "psycopg",
            "psycopg2",
            "better-sqlite3",
            "rusqlite",
            "github.com/jackc/pgx/v5",
        ):
            self.assertIn(package, profile.technologies)
            self.assertTrue(
                any(c["name"] == package and c["role"] == "client" for c in profile.components)
            )
        redis_clients = [
            c for c in profile.components if c["name"] == "redis" and c["role"] == "client"
        ]
        self.assertEqual({c["ecosystem"] for c in redis_clients}, {"npm", "pypi"})
        self.assertEqual(profile.resolved_versions["pg"], ["8.13.1"])

    def test_docker_server_versions_remain_separate_from_clients(self):
        self.write("package.json", '{"dependencies":{"pg":"^8.13","redis":"^5"}}')
        self.write(
            "compose.yaml",
            "services:\n  db:\n    image: postgres:16.4\n  cache:\n    image: redis:7.4\n",
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.resolved_versions["postgres"], ["16.4"])
        self.assertEqual(profile.resolved_versions["redis"], ["7.4"])
        candidate = Candidate(
            "database-postgres",
            "postgres16",
            "Inspect PostgreSQL query plans and transaction isolation. "
            "Parameterize statements and verify additive migrations in database tests.",
            "bundled",
            compatibility={"postgres": ">=16,<17"},
        )
        self.assertIsNone(rejection(candidate, profile))
        self.assertTrue(
            any(c["name"] == "redis" and c["role"] == "server" for c in profile.components)
        )

    def test_maven_spring_parent_properties_and_dependencies(self):
        self.write(
            "pom.xml",
            """<project xmlns="http://maven.apache.org/POM/4.0.0">
          <parent><groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-parent</artifactId><version>3.4.1</version></parent>
          <properties><java.version>21</java.version><pg.version>42.7.4</pg.version></properties>
          <dependencies><dependency><groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId></dependency>
            <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId>
              <version>${pg.version}</version></dependency></dependencies></project>""",
        )
        self.write(
            ".mvn/wrapper/maven-wrapper.properties",
            "distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/"
            "apache-maven/3.9.9/apache-maven-3.9.9-bin.zip",
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies["spring"], "3.4.1")
        self.assertEqual(profile.technologies["java"], "21")
        self.assertEqual(profile.technologies["org.postgresql:postgresql"], "42.7.4")
        self.assertEqual(profile.technologies["postgres"], "detected")
        self.assertEqual(profile.resolved_versions["maven"], ["3.9.9"])
        self.assertIn("framework-spring", profile.slots)

    def test_gradle_literal_plugin_and_dependency_versions(self):
        self.write(
            "build.gradle.kts",
            """plugins { id("org.springframework.boot") version "3.4.2" }
            java { toolchain { languageVersion = JavaLanguageVersion.of(21) } }
            dependencies { implementation("org.postgresql:postgresql:42.7.5") }""",
        )
        self.write(
            "gradle/wrapper/gradle-wrapper.properties",
            "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.12-bin.zip",
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies["spring"], "3.4.2")
        self.assertEqual(profile.technologies["java"], "21")
        self.assertEqual(profile.resolved_versions["gradle"], ["8.12"])
        self.assertEqual(profile.technologies["postgres"], "detected")

    def test_dotnet_sdk_target_aspnet_entityframework_sqlserver(self):
        self.write("global.json", '{"sdk":{"version":"8.0.404"}}')
        self.write(
            "Web.csproj",
            """<Project Sdk="Microsoft.NET.Sdk.Web">
          <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
          <ItemGroup><PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer"
            Version="8.0.11" /></ItemGroup></Project>""",
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.resolved_versions["dotnet-sdk"], ["8.0.404"])
        self.assertEqual(profile.technologies["dotnet"], "8.0")
        self.assertEqual(profile.technologies["entityframework"], "8.0.11")
        self.assertEqual(profile.technologies["sqlserver"], "detected")
        self.assertTrue(
            {"framework-aspnet", "orm-entityframework", "database-sqlserver"} <= set(profile.slots)
        )

    def test_foundry_and_hardhat_use_config_only(self):
        self.write("foundry/foundry.toml", '[profile.default]\nsolc_version="0.8.28"\n')
        self.write("package.json", '{"devDependencies":{"hardhat":"^2.22.0"}}')
        self.write("hardhat.config.ts", 'export default { solidity: "0.8.27" };')
        self.write("contracts/Ignore.sol", "pragma solidity ^0.4.0;")
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies["solidity"], "multiple")
        self.assertEqual(profile.resolved_versions["solc"], ["0.8.27", "0.8.28"])
        self.assertTrue({"language-solidity", "test-hardhat"} <= set(profile.slots))
        self.assertNotIn("contracts/Ignore.sol", profile.manifests)

    def test_plain_projects_and_comments_do_not_imply_frameworks(self):
        self.write(
            "pom.xml",
            "<project><properties><java.version>17</java.version>"
            "</properties><!-- spring-boot-starter-web --></project>",
        )
        self.write(
            "Plain.csproj",
            '<Project Sdk="Microsoft.NET.Sdk">'
            "<PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>",
        )
        self.write("build.gradle", '// id "org.springframework.boot" version "3.4.0"\n')
        profile = profile_repo(self.root)
        self.assertFalse(
            {"spring", "aspnet", "entityframework", "hardhat", "solidity"}
            & profile.technologies.keys()
        )

    def test_new_slots_have_specific_builtin_guidance(self):
        self.write("package.json", '{"devDependencies":{"hardhat":"^2.22"}}')
        for slot in (
            "framework-spring",
            "framework-aspnet",
            "orm-entityframework",
            "database-sqlserver",
            "language-solidity",
            "test-hardhat",
        ):
            self.assertIn(slot, RULES)
        self.assertTrue(bundled_candidates(profile_repo(self.root)))

    def test_untagged_server_images_and_digest_pins_have_unknown_versions(self):
        self.write(
            "compose.yaml",
            "services:\n  cache:\n    image: redis\n"
            "  db:\n    image: postgres@sha256:" + "a" * 64 + "\n",
        )
        profile = profile_repo(self.root)
        for engine in ("redis", "postgres"):
            self.assertEqual(profile.technologies[engine], "detected")
            self.assertNotIn(engine, profile.resolved_versions)
            self.assertTrue(
                any(
                    c["name"] == engine and c["role"] == "server" and c["ecosystem"] == "docker"
                    for c in profile.components
                )
            )

    def test_dotnet_multi_targets_and_explicit_server_do_not_use_provider_version(self):
        self.write(
            "Db.csproj",
            """<Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup><TargetFrameworks>net8.0;net9.0</TargetFrameworks>
            <EfVersion>9.0.1</EfVersion></PropertyGroup>
          <ItemGroup><PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer"
            Version="$(EfVersion)" /></ItemGroup></Project>""",
        )
        self.write(
            "compose.yml",
            "services:\n  db:\n    image: mcr.microsoft.com/mssql/server:2022-latest\n",
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies["dotnet"], "multiple")
        self.assertEqual(profile.technologies["entityframework"], "9.0.1")
        self.assertEqual(profile.resolved_versions["sqlserver"], ["2022-latest"])

    def test_hardhat_compiler_list_does_not_capture_unrelated_versions(self):
        self.write(
            "hardhat.config.js",
            """// solidity: "0.4.0"
            module.exports = { solidity: { compilers: [
              { version: "0.8.27", settings: { optimizer: { enabled: true } } },
              { version: "0.8.28" } ] }, other: { version: "99.0.0" } };""",
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.resolved_versions["solc"], ["0.8.27", "0.8.28"])

    def test_malformed_xml_is_reported_without_entity_expansion(self):
        self.write(
            "pom.xml",
            '<!DOCTYPE p [<!ENTITY version "3.4.0">]>'
            "<project><version>&version;</version></project>",
        )
        self.write("Broken.csproj", "<Project")
        profile = profile_repo(self.root)
        self.assertTrue(any("pom.xml: ValueError" in item for item in profile.warnings))
        self.assertTrue(any("Broken.csproj: ParseError" in item for item in profile.warnings))
