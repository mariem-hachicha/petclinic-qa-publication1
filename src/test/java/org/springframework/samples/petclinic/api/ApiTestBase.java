package org.springframework.samples.petclinic.api;

import static io.restassured.RestAssured.given;

import io.restassured.RestAssured;
import io.restassured.http.ContentType;
import io.restassured.specification.RequestSpecification;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * Base commune des tests d'API generes a partir des cas de test v3.
 * - Demarre la vraie application PetClinic sur un port libre (base H2 en memoire).
 * - Active la securite JWT pour ces tests (les cas verifient les roles et les jetons).
 * - Fournit request(user) : une requete deja authentifiee avec le jeton de cet utilisateur.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "petclinic.security.enable=true")
public abstract class ApiTestBase {

    /** Jetons deja obtenus, pour ne pas refaire un login a chaque test. */
    private static final Map<String, String> TOKENS = new ConcurrentHashMap<>();

    @Value("${local.server.port}")
    private int port;

    @Value("${server.servlet.context-path:}")
    private String contextPath;

    @BeforeEach
    void configureRestAssured() {
        RestAssured.port = port;
        // "/petclinic/" -> "/petclinic" ; les chemins des cas commencent deja par "/api/...".
        RestAssured.basePath = contextPath.endsWith("/")
                ? contextPath.substring(0, contextPath.length() - 1)
                : contextPath;
    }

    /** Jeton JWT d'un utilisateur de demo (mot de passe = nom d'utilisateur, cf. requirements.json). */
    protected String tokenOf(String user) {
        return TOKENS.computeIfAbsent(user, u -> given()
                .contentType(ContentType.JSON)
                .body(Map.of("username", u, "password", u))
                .when().post("/api/auth/login")
                .then().statusCode(200)
                .extract().path("accessToken"));
    }

    /** Requete preparee : avec le jeton de 'user', ou sans authentification si user est null. */
    protected RequestSpecification request(String user) {
        RequestSpecification spec = given().contentType(ContentType.JSON).accept(ContentType.JSON);
        return user == null ? spec : spec.auth().oauth2(tokenOf(user));
    }
}