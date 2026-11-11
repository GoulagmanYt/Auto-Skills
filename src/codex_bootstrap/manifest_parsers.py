"""Pure bounded text parsers sharing adapters.Evidence; project code is never executed."""

import re
import xml.etree.ElementTree as ET

from .adapters import Evidence


def _xml_manifest(text):
    # No entity expansion or external definitions are needed in a build manifest.
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise ValueError("XML declarations are unsupported")
    tree = ET.fromstring(text)
    for element in tree.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    return tree


def _property_value(value, properties):
    value = value or "detected"
    for _ in range(8):
        if len(value) > 100:
            return "unresolved"
        resolved = re.sub(
            r"\$\{([^}]+)\}|\$\(([^)]+)\)", lambda m: properties.get(m[1] or m[2], m[0]), value
        )
        if resolved == value:
            break
        value = resolved
    return "unresolved" if "$" in value else value


def _without_build_comments(text):
    """Remove comments without executing config or interpreting quoted strings."""
    pattern = r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//[^\n]*|/\*[\s\S]*?\*/"""
    return re.sub(pattern, lambda m: " " if m[0].startswith(("//", "/*")) else m[0], text)


def _jvm_dependency(group, artifact, version, ecosystem):
    result = []
    if not group or not artifact:
        return result
    result.append(Evidence(f"{group}:{artifact}", version, ecosystem=ecosystem))
    if group == "org.springframework.boot" and artifact.startswith("spring-boot"):
        result.append(Evidence("spring", version, ecosystem=ecosystem))
    elif group == "org.springframework" and artifact.startswith("spring-"):
        result.append(Evidence("spring", version, ecosystem=ecosystem))
    return result


def maven_manifest(text):
    result = []
    tree = _xml_manifest(text)
    properties = {
        element.tag: (element.text or "").strip() for element in tree.findall("./properties/*")
    }
    for key in ("java.version", "maven.compiler.release", "maven.compiler.target"):
        if key in properties:
            result.append(
                Evidence("java", _property_value(properties[key], properties), ecosystem="maven")
            )
            break
    for dependency in tree.findall(".//dependency") + tree.findall("./parent"):
        group = dependency.findtext("groupId", "").strip()
        artifact = dependency.findtext("artifactId", "").strip()
        version = _property_value(dependency.findtext("version"), properties)
        result.extend(_jvm_dependency(group, artifact, version, "maven"))
    return result


def gradle_manifest(text):
    result = []
    text = _without_build_comments(text)
    for version in re.findall(
        "\\bid\\s*(?:\\(\\s*)?[\"']org\\.springframework\\.boot[\"']\\s*\\)?\\s*version\\s*[\"']([^\"']+)[\"']",
        text,
    ):
        result.append(Evidence("spring", version, ecosystem="gradle"))
    for group, artifact, version in re.findall(
        "\\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation|classpath)\\s*(?:\\(\\s*)?[\"']([\\w.-]+):([\\w.-]+):([^\"']+)[\"']",
        text,
    ):
        result.extend(
            _jvm_dependency(group, artifact, "unresolved" if "$" in version else version, "gradle")
        )
    java = re.search("JavaLanguageVersion\\.of\\(\\s*(\\d+)\\s*\\)", text)
    if not java:
        java = re.search(
            "\\b(?:sourceCompatibility|targetCompatibility)\\s*=\\s*(?:JavaVersion\\.VERSION_)?[\"']?(\\d+(?:\\.\\d+)?)",
            text,
        )
    if java:
        result.append(Evidence("java", java[1], ecosystem="gradle"))
    return result


def dotnet_manifest(text):
    result = []
    tree = _xml_manifest(text)
    properties = {
        element.tag: (element.text or "").strip() for element in tree.findall("./PropertyGroup/*")
    }
    sdk = tree.get("Sdk", "").lower()
    web = "microsoft.net.sdk.web" in sdk or any(
        element.get("Name", "").lower() == "microsoft.net.sdk.web"
        for element in tree.findall("./Sdk")
    )
    if web:
        result.append(Evidence("aspnet", ecosystem="nuget"))
    for framework in (
        properties.get("TargetFramework") or properties.get("TargetFrameworks", "")
    ).split(";"):
        target = re.fullmatch("net(\\d+\\.\\d+)(?:-[\\w.-]+)?", framework.strip())
        if target:
            result.append(Evidence("dotnet", target[1], ecosystem="nuget"))
            if web:
                result.append(Evidence("aspnet", target[1], ecosystem="nuget"))
    if properties.get("RuntimeFrameworkVersion"):
        result.append(
            Evidence(
                "dotnet",
                _property_value(properties["RuntimeFrameworkVersion"], properties),
                kind="runtime",
                ecosystem="nuget",
            )
        )
    for reference in tree.findall(".//PackageReference"):
        package = reference.get("Include", reference.get("Update", ""))
        if not package:
            continue
        version = _property_value(
            reference.get("Version") or reference.findtext("Version"), properties
        )
        result.append(Evidence(package, version, ecosystem="nuget"))
        if package.lower().startswith("microsoft.entityframeworkcore"):
            result.append(Evidence("entityframework", version, ecosystem="nuget"))
        if package.lower().startswith("microsoft.aspnetcore"):
            result.append(Evidence("aspnet", version, ecosystem="nuget"))
    for reference in tree.findall(".//FrameworkReference"):
        if reference.get("Include", "").lower() == "microsoft.aspnetcore.app":
            result.append(Evidence("aspnet", ecosystem="nuget"))
    return result


def hardhat_manifest(text):
    result = []
    text = _without_build_comments(text)
    match = re.search("\\bsolidity\\s*:\\s*(?:[\"'](\\d+\\.\\d+\\.\\d+)[\"']|\\{)", text)
    versions = []
    if match and match[1]:
        versions.append(match[1])
    elif match:
        depth, end = (1, match.end())
        tokens = re.finditer("\"(?:\\\\.|[^\"\\\\])*\"|'(?:\\\\.|[^'\\\\])*'|[{}]", text[end:])
        for token in tokens:
            if token[0] == "{":
                depth += 1
            elif token[0] == "}":
                depth -= 1
                if depth == 0:
                    end += token.start()
                    break
        else:
            return result
        versions.extend(
            re.findall("\\bversion\\s*:\\s*[\"'](\\d+\\.\\d+\\.\\d+)[\"']", text[match.end() : end])
        )
    result.append(Evidence("hardhat", kind="detection"))
    for version in versions:
        result.append(Evidence("solidity", version))
        result.append(Evidence("solc", version, kind="runtime"))
    return result


PARSERS = {
    "pom.xml": maven_manifest,
    "build.gradle": gradle_manifest,
    "build.gradle.kts": gradle_manifest,
}


def extract_manifest(name, text):
    parser = PARSERS.get(name)
    if name.endswith(".csproj"):
        parser = dotnet_manifest
    elif name.startswith("hardhat.config."):
        parser = hardhat_manifest
    return None if parser is None else parser(text)
