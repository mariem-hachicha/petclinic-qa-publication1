package org.springframework.samples.petclinic.api;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** Verifie que la base des tests d'API fonctionne (demarrage, login, jeton, 401). */
class ApiSmokeTest extends ApiTestBase {

    @Test
    void loginAdminRenvoieUnJeton() {
        assertThat(tokenOf("admin")).isNotBlank();
    }

    @Test
    void unVeterinairePeutListerLesProprietaires() {
        request("vet").when().get("/api/owners").then().statusCode(200);
    }

    @Test
    void sansJetonLaRequeteEstRefusee() {
        request(null).when().get("/api/owners").then().statusCode(401);
    }
}