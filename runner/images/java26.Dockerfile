# Java runner image on JDK 26 (D52: version check of the S4 result; solutions compiled on JDK 25 are run unchanged). Build context: repository root.
FROM maven:3.9-eclipse-temurin-25@sha256:93b8a14ea2f412782e4e842651273b4d903e35cc496284f178fbbe2d67d00976 AS libs
COPY runner/java/libs/pom.xml /w/pom.xml
RUN cd /w && mvn -q -B dependency:copy-dependencies -DoutputDirectory=/lib \
 && cd /lib && sha256sum *.jar > /lcr-java-jars.sha256

FROM eclipse-temurin@sha256:9c0e8eddecccc0d5679b317b0c90fa7103ad25cae33df1c00280675eb681c7f8
COPY --from=libs /lib /opt/lcr-java/lib
COPY --from=libs /lcr-java-jars.sha256 /etc/lcr-java-jars.sha256
COPY runner/java/driver /opt/lcr-java/src
RUN javac --release 25 -cp "/opt/lcr-java/lib/*" -d /opt/lcr-java/harness /opt/lcr-java/src/lcr/*.java \
 && printf '#!/bin/sh\nexec java -cp "/opt/lcr-java/harness:/opt/lcr-java/lib/*" lcr.Prepare\n' > /opt/lcr-java/prepare.sh \
 && chmod 755 /opt/lcr-java/prepare.sh
# Test CA in the JDK truststore (used by HttpClient, OkHttp, Apache HttpClient).
COPY certs/ca.pem /tmp/lcr-ca.pem
RUN keytool -importcert -cacerts -storepass changeit -noprompt -alias lcr-test-ca -file /tmp/lcr-ca.pem >/dev/null \
 && rm /tmp/lcr-ca.pem
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["java", "-cp", "/opt/lcr-java/harness:/opt/lcr-java/lib/*:/solution/classes", "lcr.Driver"]
